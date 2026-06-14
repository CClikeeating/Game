const tabbar = require("../../utils/tabbar")

Page({
  onShow() {
    tabbar.setSelected(this, 1)
  }
})
