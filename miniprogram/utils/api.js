const app = getApp()

function baseUrl() {
  return app.globalData.apiBaseUrl.replace(/\/$/, "")
}

function token() {
  return app.globalData.token || wx.getStorageSync("baiou_token") || ""
}

function networkErrorMessage(errMsg) {
  if ((errMsg || "").indexOf("fail") >= 0) {
    return "后端服务未连接，请先启动本地 API"
  }
  return errMsg || "网络失败"
}

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl()}${path}`,
      method: options.method || "GET",
      data: options.data || {},
      timeout: options.timeout || 120000,
      header: {
        "content-type": "application/json",
        Authorization: token() ? `Bearer ${token()}` : ""
      },
      success(res) {
        const data = res.data || {}
        if (res.statusCode >= 200 && res.statusCode < 300 && data.ok !== false) {
          resolve(data)
        } else {
          reject(data.error || { code: "request_failed", message: "请求失败" })
        }
      },
      fail(err) {
        reject({ code: "network_failed", message: networkErrorMessage(err.errMsg) })
      }
    })
  })
}

function uploadImage(filePath) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${baseUrl()}/api/v1/uploads`,
      filePath,
      name: "file",
      timeout: 120000,
      header: {
        Authorization: token() ? `Bearer ${token()}` : ""
      },
      success(res) {
        let data = {}
        try {
          data = JSON.parse(res.data || "{}")
        } catch (err) {
          reject({ code: "invalid_upload_response", message: "上传返回异常" })
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300 && data.ok !== false) {
          resolve(data.upload)
        } else {
          reject(data.error || { code: "upload_failed", message: "上传失败" })
        }
      },
      fail(err) {
        reject({ code: "upload_failed", message: networkErrorMessage(err.errMsg) })
      }
    })
  })
}

module.exports = { request, uploadImage }
