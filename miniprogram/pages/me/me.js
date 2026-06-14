const api = require("../../utils/api")
const tabbar = require("../../utils/tabbar")
const app = getApp()

Page({
  data: {
    user: {},
    limits: app.globalData.limits || {},
    announcements: [],
    products: [],
    paymentEnabled: false
  },

  onShow() {
    tabbar.setSelected(this, 2)
    this.load()
  },

  async load() {
    try {
      if (!app.globalData.token) {
        const login = await api.request("/api/v1/auth/login", { method: "POST", data: {} })
        app.globalData.token = login.token
        app.globalData.user = login.user || app.globalData.user
        app.globalData.limits = login.limits || app.globalData.limits
        wx.setStorageSync("baiou_token", login.token)
      }
      const me = await api.request("/api/v1/me")
      const announcements = await api.request("/api/v1/announcements")
      const billing = await api.request("/api/v1/billing/products")
      this.setData({
        user: me.user || {},
        limits: me.limits || app.globalData.limits || {},
        announcements: announcements.announcements || [],
        products: billing.products || [],
        paymentEnabled: !!billing.payment_enabled
      })
    } catch (err) {
      this.setData({ limits: app.globalData.limits || this.data.limits })
      wx.showToast({ title: err.message || "加载失败", icon: "none" })
    }
  }
})
