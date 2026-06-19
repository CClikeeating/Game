const api = require("../../utils/api")
const tabbar = require("../../utils/tabbar")
const app = getApp()

const MODE_FAST = "bailian_rag_fast"
const MODE_STRATEGY_QUALITY = "bailian_rag_strategy_quality"
const ALLOWED_MODES = [MODE_FAST, MODE_STRATEGY_QUALITY]

function normalizeMode(mode) {
  return ALLOWED_MODES.includes(mode) ? mode : MODE_FAST
}

function modeCosts(limits = {}) {
  const costs = limits.mode_unit_costs || {}
  return {
    fastCost: costs[MODE_FAST] || 1,
    strategyCost: costs[MODE_STRATEGY_QUALITY] || 2
  }
}

Page({
  data: {
    question: "我该怎么回",
    context: "",
    entryType: "screenshot",
    mode: MODE_STRATEGY_QUALITY,
    fastCost: 1,
    strategyCost: 2,
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
    analysisOpen: false
  },

  onShow() {
    tabbar.setSelected(this, 0)
    this.ensureSession()
  },

  async ensureSession() {
    try {
      await api.ensureLogin()
      await this.refreshSessionData()
    } catch (err) {
      try {
        await api.reloginAfterAuthError(err)
        await this.refreshSessionData()
      } catch (retryErr) {
        this.setData({ limits: app.globalData.limits || this.data.limits, serviceReady: false })
        this.toast(retryErr.message || "初始化失败")
      }
    }
  },

  async refreshSessionData() {
    const me = await api.request("/api/v1/me")
    await this.loadConversations()
    const limits = me.limits || app.globalData.limits || {}
    this.setData({ limits, ...modeCosts(limits), serviceReady: true })
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
          data: { title: this.data.draftTitle || "新窗口", background: this.data.draftBackground }
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
      const limits = me.limits || this.data.limits
      this.setData({ limits, ...modeCosts(limits), serviceReady: true })
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

  selectEntry(e) {
    const entryType = e.currentTarget.dataset.entry || "text_only"
    const update = { entryType }
    if (entryType === "text_only") {
      update.mode = MODE_FAST
      update.images = []
    } else {
      update.mode = MODE_STRATEGY_QUALITY
    }
    this.setData(update)
  },

  selectMode(e) {
    if (this.data.entryType === "text_only") return
    this.setData({ mode: normalizeMode(e.currentTarget.dataset.mode) })
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
      this.toast("请先创建窗口")
      return
    }
    if (!this.data.question.trim()) {
      this.toast("请输入用户问题")
      return
    }
    const textOnly = this.data.entryType === "text_only"
    if (!textOnly && !this.data.images.length) {
      this.toast("请上传截图")
      return
    }
    this.setData({ loading: true })
    try {
      const uploads = []
      if (!textOnly) {
        for (const image of this.data.images) {
          const uploaded = await api.uploadImage(image.tempFilePath)
          uploads.push(uploaded.upload_id)
        }
      }
      const mode = textOnly ? MODE_FAST : normalizeMode(this.data.mode)
      const data = await api.request("/api/v1/replies", {
        method: "POST",
        data: {
          conversation_id: this.data.currentConversation.conversation_id,
          question: this.data.question,
          context: this.data.context,
          mode,
          input_type: textOnly ? "text_only" : "screenshot",
          upload_ids: uploads
        }
      })
      const limits = data.limits || this.data.limits
      this.setData({
        result: data.reply_run,
        limits,
        ...modeCosts(limits),
        images: [],
        feedbackNotes: "",
        analysisOpen: false
      })
    } catch (err) {
      this.toast(err.message || "处理失败")
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
