const envConfig = require("./config/env")

function resolveApiBaseUrl() {
  const override = wx.getStorageSync("baiou_api_base_url")
  if (override) return override
  const account = wx.getAccountInfoSync ? wx.getAccountInfoSync() : {}
  const env = account.miniProgram && account.miniProgram.envVersion || envConfig.defaultEnv
  return envConfig.apiBaseUrls[env] || envConfig.apiBaseUrls[envConfig.defaultEnv]
}

App({
  globalData: {
    apiBaseUrl: "",
    token: "",
    user: null,
    limits: {},
    currentConversationId: ""
  },

  onLaunch() {
    this.globalData.apiBaseUrl = resolveApiBaseUrl()
    const token = wx.getStorageSync("baiou_token")
    const currentConversationId = wx.getStorageSync("baiou_current_conversation_id")
    if (token) this.globalData.token = token
    if (currentConversationId) this.globalData.currentConversationId = currentConversationId
  }
})
