/** Plays ElevenLabs audio and drives the Live2D mouth from its actual amplitude. */
export class AmiVoice {
  /** @param {(value:number)=>void} onMouth @param {(state:string)=>void} onState */
  constructor(onMouth, onState) {
    this.onMouth = onMouth;
    this.onState = onState;
    /** @type {AudioContext|null} */
    this.context = null;
    /** @type {AudioBufferSourceNode|null} */
    this.source = null;
    /** @type {AnalyserNode|null} */
    this.analyser = null;
    /** @type {AbortController|null} */
    this.request = null;
    /** @type {Map<number,AudioBuffer>} */
    this.cache = new Map();
    this.frameId = 0;
    this.generation = 0;
  }

  async unlock() {
    if (!globalThis.AudioContext) throw new Error('Trình duyệt không hỗ trợ phát giọng nói. Bạn vẫn có thể đọc câu trả lời.');
    if (!this.context) this.context = new AudioContext();
    await this.context.resume();
  }

  /** @param {number} messageId */
  async speak(messageId) {
    this.stop();
    const generation = this.generation;
    await this.unlock();
    if (generation !== this.generation) return;
    this.onState('loading');
    this.request = new AbortController();
    try {
      let buffer = this.cache.get(messageId);
      if (!buffer) {
        const response = await fetch('/api/chat/' + messageId + '/speech', {method:'POST',signal:this.request.signal});
        if (!response.ok) {
          const error = await response.json();
          throw new Error(typeof error.detail==='string' ? error.detail : 'Chưa tạo được giọng nói.');
        }
        if (!response.headers.get('content-type')?.startsWith('audio/')) throw new Error('Máy chủ chưa trả về âm thanh hợp lệ.');
        buffer = await this.context.decodeAudioData(await response.arrayBuffer());
        if (generation !== this.generation) return;
        if (this.cache.size >= 4) this.cache.delete(this.cache.keys().next().value);
        this.cache.set(messageId,buffer);
      }
      if (generation !== this.generation) return;
      this.source = this.context.createBufferSource();
      this.source.buffer = buffer;
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 256;
      this.source.connect(this.analyser);
      this.analyser.connect(this.context.destination);
      const source = this.source;
      source.onended = () => { if(this.source===source)this.stop(); };
      const samples = new Uint8Array(this.analyser.fftSize);
      const animate = () => {
        if(generation!==this.generation||!this.analyser)return;
        this.analyser.getByteTimeDomainData(samples);
        const energy = Math.sqrt(samples.reduce((sum,value)=>sum+((value-128)/128)**2,0)/samples.length);
        this.onMouth(Math.min(1,energy*7));
        this.frameId = requestAnimationFrame(animate);
      };
      source.start();
      this.onState('speaking');
      this.frameId=requestAnimationFrame(animate);
    } catch(error) {
      if(generation!==this.generation||error.name==='AbortError')return;
      this.stop();
      throw error;
    }
  }

  stop() {
    this.generation++;
    this.request?.abort();
    this.request=null;
    cancelAnimationFrame(this.frameId);
    if(this.source){this.source.onended=null;this.source.stop();this.source.disconnect();this.source=null;}
    this.analyser?.disconnect();
    this.analyser=null;
    this.onMouth(0);
    this.onState('idle');
  }

  clear() { this.stop();this.cache.clear(); }
}
