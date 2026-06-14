Component({
  data: {
    selected: 0,
    list: [
      { pagePath: "/pages/reply/reply", text: "聊天" },
      { pagePath: "/pages/library/library", text: "话术库" },
      { pagePath: "/pages/me/me", text: "我的" }
    ]
  },

  methods: {
    switchTab(e) {
      const { path } = e.currentTarget.dataset
      wx.switchTab({ url: path })
    }
  }
})
