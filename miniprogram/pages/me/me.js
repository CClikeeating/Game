const api = require("../../utils/api")
const tabbar = require("../../utils/tabbar")
const app = getApp()

Page({
  data: {
    user: {},
    limits: app.globalData.limits || {},
    announcements: [],
    products: [],
    paymentEnabled: false,
    contactQq: "1179123330",
    redeemCode: "",
    timePassText: "暂无有效权益",
    redeeming: false
  },

  onShow() {
    tabbar.setSelected(this, 2)
    this.load()
  },

  async load() {
    try {
      await api.ensureLogin()
      await this.refreshPageData()
    } catch (err) {
      try {
        await api.reloginAfterAuthError(err)
        await this.refreshPageData()
      } catch (retryErr) {
        this.setData({ limits: app.globalData.limits || this.data.limits })
        wx.showToast({ title: retryErr.message || "加载失败", icon: "none" })
      }
    }
  },

  async refreshPageData() {
    const me = await api.request("/api/v1/me")
    const announcements = await api.request("/api/v1/announcements")
    const billing = await api.request("/api/v1/billing/products")
    app.globalData.limits = me.limits || app.globalData.limits || {}
    this.setData({
      user: me.user || {},
      limits: app.globalData.limits,
      timePassText: formatTimePass(me.limits || {}),
      announcements: announcements.announcements || [],
      products: billing.products || [],
      paymentEnabled: !!billing.payment_enabled,
      contactQq: billing.contact_qq || "1179123330"
    })
  },

  onRedeemCodeInput(e) {
    this.setData({ redeemCode: e.detail.value })
  },

  async submitRedeemCode() {
    const code = this.data.redeemCode.trim()
    if (!code) {
      wx.showToast({ title: "请输入兑换码", icon: "none" })
      return
    }
    this.setData({ redeeming: true })
    try {
      const data = await api.request("/api/v1/redeem-codes/redeem", {
        method: "POST",
        data: { code }
      })
      this.setData({ limits: data.limits || this.data.limits, redeemCode: "" })
      wx.showToast({ title: "兑换成功", icon: "none" })
    } catch (err) {
      wx.showToast({ title: err.message || "兑换失败", icon: "none" })
    } finally {
      this.setData({ redeeming: false })
    }
  }
})

function formatTimePass(limits = {}) {
  if (!limits.time_pass_active || !limits.time_pass_expires_at) return "暂无有效权益"
  return `有效至 ${limits.time_pass_expires_at}`
}
