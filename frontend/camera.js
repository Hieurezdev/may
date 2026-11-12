/** Owns one camera stream and releases it when stopped or superseded. */
export class LiveCamera {
  /** @param {HTMLVideoElement} video @param {()=>void} onFrame @param {()=>void} onEnded */
  constructor(video, onFrame, onEnded) {
    this.video = video;
    this.onFrame = onFrame;
    this.onEnded = onEnded;
    /** @type {MediaStream|null} */
    this.stream = null;
    this.frameId = 0;
    this.generation = 0;
    this.deviceCount = 0;
    /** @type {AbortController|null} */
    this.listeners = null;
  }

  get active() { return this.stream !== null; }

  /** @param {'user'|'environment'} facingMode @returns {Promise<boolean>} */
  async start(facingMode) {
    this.stop();
    const generation = this.generation;
    if (!globalThis.isSecureContext) {
      throw new Error('Camera cần HTTPS hoặc localhost. Hãy mở địa chỉ HTTPS của cửa hàng.');
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Trình duyệt chưa hỗ trợ camera. Hãy dùng phiên bản mới của Chrome, Edge hoặc Safari.');
    }
    /** @type {MediaStream|null} */
    let acquired = null;
    try {
      acquired = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: facingMode }, width: { ideal: 1280 }, height: { ideal: 960 }, frameRate: { ideal: 30, max: 30 } },
      });
      if (generation !== this.generation) {
        acquired.getTracks().forEach(track => track.stop());
        return false;
      }
      this.stream = acquired;
      this.listeners = new AbortController();
      acquired.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        this.stop();
        this.onEnded();
      }, { signal: this.listeners.signal }));
      this.video.srcObject = acquired;
      await this.video.play();
      const devices = await navigator.mediaDevices.enumerateDevices();
      if (generation !== this.generation) return false;
      this.deviceCount = devices.filter(device => device.kind === 'videoinput').length;
      const frame = () => {
        if (generation !== this.generation || !this.stream) return;
        if (this.video.readyState >= 2) this.onFrame();
        this.frameId = requestAnimationFrame(frame);
      };
      this.frameId = requestAnimationFrame(frame);
      return true;
    } catch (error) {
      if (generation !== this.generation) return false;
      this.stop();
      if (error.name === 'NotAllowedError') throw new Error('Camera chưa được cấp quyền. Cho phép camera trong trình duyệt rồi chọn Bật camera lại.');
      if (error.name === 'NotFoundError') throw new Error('Không tìm thấy camera. Hãy kết nối camera hoặc mở cửa hàng trên điện thoại.');
      if (error.name === 'NotReadableError') throw new Error('Không đọc được camera. Đóng ứng dụng đang dùng camera rồi thử lại.');
      throw error;
    }
  }

  stop() {
    this.generation++;
    cancelAnimationFrame(this.frameId);
    this.frameId = 0;
    this.listeners?.abort();
    this.listeners = null;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    this.video.pause();
    this.video.srcObject = null;
  }
}
