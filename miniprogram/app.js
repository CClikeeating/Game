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
    limits: {
      max_conversations_per_user: 5,
      history_turns_for_reply: 6,
      daily_reply_quota: 10,
      daily_reply_remaining: 10,
      mode_unit_costs: {
        bailian_rag_fast: 1,
        bailian_rag_strategy_quality: 2
      },
      max_images_per_reply: 3,
      min_images_per_reply: 1,
      max_image_mb: 8
    },
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
