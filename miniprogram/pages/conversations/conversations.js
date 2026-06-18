const api = require("../../utils/api")
const app = getApp()

Page({
  data: {
    conversations: [],
    limits: {},
    title: "",
    background: "",
    editingId: ""
  },

  onShow() {
    this.init()
  },

  async init() {
    try {
      if (!app.globalData.token) {
        const login = await this.loginWithWechatCode()
        app.globalData.token = login.token
        wx.setStorageSync("baiou_token", login.token)
      }
      const me = await api.request("/api/v1/me")
      const data = await api.request("/api/v1/conversations")
      this.setData({ limits: me.limits || {}, conversations: data.conversations || [] })
    } catch (err) {
      this.toast(err.message || "加载失败")
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
            reject(err)
          }
        },
        fail: () => {
          reject({ message: "微信登录失败，请稍后重试" })
        }
      })
    })
  },

  onTitleInput(e) {
    this.setData({ title: e.detail.value })
  },

  onBackgroundInput(e) {
    this.setData({ background: e.detail.value })
  },

  async createConversation() {
    try {
      if (this.data.editingId) {
        await api.request(`/api/v1/conversations/${this.data.editingId}`, {
          method: "PATCH",
          data: { title: this.data.title, background: this.data.background }
        })
      } else {
        await api.request("/api/v1/conversations", {
          method: "POST",
          data: { title: this.data.title || "新的聊天", background: this.data.background }
        })
      }
      this.setData({ title: "", background: "", editingId: "" })
      await this.init()
    } catch (err) {
      this.toast(err.message || "保存失败")
    }
  },

  editConversation(e) {
    this.setData({
      editingId: e.currentTarget.dataset.id,
      title: e.currentTarget.dataset.title || "",
      background: e.currentTarget.dataset.background || ""
    })
  },

  selectConversation(e) {
    const id = e.currentTarget.dataset.id
    app.globalData.currentConversationId = id
    wx.setStorageSync("baiou_current_conversation_id", id)
    wx.switchTab({ url: "/pages/reply/reply" })
  },

  async deleteConversation(e) {
    try {
      await api.request(`/api/v1/conversations/${e.currentTarget.dataset.id}`, { method: "DELETE" })
      await this.init()
    } catch (err) {
      this.toast(err.message || "归档失败")
    }
  },

  toast(title) {
    wx.showToast({ title, icon: "none" })
  }
})
