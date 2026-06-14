App({
  globalData: {
    apiBaseUrl: "http://127.0.0.1:7871",
    token: "",
    user: null,
    limits: {
      max_conversations_per_user: 5,
      history_turns_for_reply: 6,
      daily_reply_quota: 20,
      daily_reply_remaining: 20,
      max_images_per_reply: 3,
      min_images_per_reply: 1,
      max_image_mb: 8
    },
    currentConversationId: ""
  },

  onLaunch() {
    const token = wx.getStorageSync("baiou_token")
    const currentConversationId = wx.getStorageSync("baiou_current_conversation_id")
    if (token) this.globalData.token = token
    if (currentConversationId) this.globalData.currentConversationId = currentConversationId
  }
})
