const api = require("../../utils/api")
const tabbar = require("../../utils/tabbar")
const app = getApp()

Page({
  data: {
    question: "我该怎么回",
    context: "",
    mode: "bailian_rag_fast",
    images: [],
    conversations: [],
    currentConversation: {},
    limits: app.globalData.limits || {},
    serviceReady: false,
    result: null,
    feedbackNotes: "",
    loading: false,
    drawerOpen: false,
    draftTitle: "",
    draftBackground: "",
    editingId: "",
    analysisOpen: false,
    debugOpen: false
  },

  onShow() {
    tabbar.setSelected(this, 0)
    this.ensureSession()
  },

  async ensureSession() {
    try {
      if (!app.globalData.token) {
        const login = await this.loginWithWechatCode()
        app.globalData.token = login.token
        app.globalData.user = login.user
        app.globalData.limits = login.limits || app.globalData.limits
        wx.setStorageSync("baiou_token", login.token)
      }
      const me = await api.request("/api/v1/me")
      await this.loadConversations()
      this.setData({ limits: me.limits || app.globalData.limits || {}, serviceReady: true })
    } catch (err) {
      this.setData({ limits: app.globalData.limits || this.data.limits, serviceReady: false })
      this.toast(err.message || "初始化失败")
    }
  },

  loginWithWechatCode() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: async res => {
          try {
            const login = await api.request("/api/v1/auth/login", { method: "POST", data: { code: res.code } })
            resolve(login)
          } catch (err) {
            try {
              const fallback = await api.request("/api/v1/auth/login", { method: "POST", data: {} })
              resolve(fallback)
            } catch (fallbackErr) {
              reject(fallbackErr)
            }
          }
        },
        fail: async () => {
          try {
            const fallback = await api.request("/api/v1/auth/login", { method: "POST", data: {} })
            resolve(fallback)
          } catch (fallbackErr) {
            reject(fallbackErr)
          }
        }
      })
    })
  },

  async loadConversations() {
    const data = await api.request("/api/v1/conversations")
    const conversations = data.conversations || []
    const currentId = app.globalData.currentConversationId || wx.getStorageSync("baiou_current_conversation_id")
    const current = conversations.find(item => item.conversation_id === currentId) || conversations[0] || {}
    if (current.conversation_id) {
      app.globalData.currentConversationId = current.conversation_id
      wx.setStorageSync("baiou_current_conversation_id", current.conversation_id)
    }
    this.setData({ conversations, currentConversation: current })
  },

  openDrawer() {
    this.setData({ drawerOpen: true })
  },

  closeDrawer() {
    this.setData({ drawerOpen: false })
  },

  startNewConversation() {
    this.setData({ drawerOpen: true, editingId: "", draftTitle: "", draftBackground: "" })
  },

  onDraftTitleInput(e) {
    this.setData({ draftTitle: e.detail.value })
  },

  onDraftBackgroundInput(e) {
    this.setData({ draftBackground: e.detail.value })
  },

  async saveConversation() {
    try {
      if (this.data.editingId) {
        await api.request(`/api/v1/conversations/${this.data.editingId}`, {
          method: "PATCH",
          data: { title: this.data.draftTitle, background: this.data.draftBackground }
        })
      } else {
        const data = await api.request("/api/v1/conversations", {
          method: "POST",
          data: { title: this.data.draftTitle || "新的聊天", background: this.data.draftBackground }
        })
        const id = data.conversation && data.conversation.conversation_id
        if (id) {
          app.globalData.currentConversationId = id
          wx.setStorageSync("baiou_current_conversation_id", id)
        }
      }
      this.setData({ draftTitle: "", draftBackground: "", editingId: "" })
      await this.loadConversations()
      const me = await api.request("/api/v1/me")
      this.setData({ limits: me.limits || this.data.limits, serviceReady: true })
    } catch (err) {
      this.toast(err.message || "保存失败")
    }
  },

  editConversation(e) {
    this.setData({
      editingId: e.currentTarget.dataset.id,
      draftTitle: e.currentTarget.dataset.title || "",
      draftBackground: e.currentTarget.dataset.background || "",
      drawerOpen: true
    })
  },

  selectConversation(e) {
    const id = e.currentTarget.dataset.id
    const current = this.data.conversations.find(item => item.conversation_id === id) || {}
    app.globalData.currentConversationId = id
    wx.setStorageSync("baiou_current_conversation_id", id)
    this.setData({ currentConversation: current, drawerOpen: false, result: null })
  },

  async deleteConversation(e) {
    try {
      await api.request(`/api/v1/conversations/${e.currentTarget.dataset.id}`, { method: "DELETE" })
      await this.loadConversations()
    } catch (err) {
      this.toast(err.message || "归档失败")
    }
  },

  onQuestionInput(e) {
    this.setData({ question: e.detail.value })
  },

  onContextInput(e) {
    this.setData({ context: e.detail.value })
  },

  onFeedbackNotesInput(e) {
    this.setData({ feedbackNotes: e.detail.value })
  },

  selectMode(e) {
    this.setData({ mode: e.currentTarget.dataset.mode })
  },

  chooseImages() {
    const max = this.data.limits.max_images_per_reply || 3
    const remaining = Math.max(0, max - this.data.images.length)
    if (!remaining) {
      this.toast(`一次最多 ${max} 张截图`)
      return
    }
    wx.chooseMedia({
      count: remaining,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["compressed"],
      success: res => {
        const maxBytes = (this.data.limits.max_image_mb || 8) * 1024 * 1024
        const selected = (res.tempFiles || []).filter(item => item.size <= maxBytes).map(item => ({
          tempFilePath: item.tempFilePath,
          size: item.size,
          sizeText: `${Math.ceil(item.size / 1024)} KB`
        }))
        if (selected.length !== (res.tempFiles || []).length) this.toast("已忽略超大图片")
        this.setData({ images: this.data.images.concat(selected).slice(0, max) })
      }
    })
  },

  removeImage(e) {
    const index = e.currentTarget.dataset.index
    const images = this.data.images.slice()
    images.splice(index, 1)
    this.setData({ images })
  },

  async submitReply() {
    if (!this.data.currentConversation.conversation_id) {
      this.toast("请先创建聊天窗口")
      return
    }
    if (!this.data.question.trim()) {
      this.toast("请输入用户问题")
      return
    }
    if (!this.data.images.length) {
      this.toast("请上传聊天截图")
      return
    }
    this.setData({ loading: true })
    try {
      const uploads = []
      for (const image of this.data.images) {
        const uploaded = await api.uploadImage(image.tempFilePath)
        uploads.push(uploaded.upload_id)
      }
      const data = await api.request("/api/v1/replies", {
        method: "POST",
        data: {
          conversation_id: this.data.currentConversation.conversation_id,
          question: this.data.question,
          context: this.data.context,
          mode: this.data.mode,
          upload_ids: uploads
        }
      })
      this.setData({
        result: data.reply_run,
        limits: data.limits || this.data.limits,
        images: [],
        feedbackNotes: "",
        analysisOpen: false,
        debugOpen: false
      })
    } catch (err) {
      this.toast(err.message || "生成失败")
    } finally {
      this.setData({ loading: false })
    }
  },

  toggleFold(e) {
    const key = e.currentTarget.dataset.key
    this.setData({ [key]: !this.data[key] })
  },

  async sendFeedback(e) {
    if (!this.data.result) return
    try {
      await api.request("/api/v1/feedback", {
        method: "POST",
        data: {
          conversation_id: this.data.currentConversation.conversation_id,
          run_id: this.data.result.run_id,
          rating: e.currentTarget.dataset.rating,
          notes: this.data.feedbackNotes
        }
      })
      this.toast("已记录")
    } catch (err) {
      this.toast(err.message || "反馈失败")
    }
  },

  toast(title) {
    wx.showToast({ title, icon: "none" })
  }
})
