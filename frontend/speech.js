import { api, esc } from './api.js';
import { icon } from './icons.js';

/** @param {HTMLDialogElement} dialog @param {(text:string)=>void} onSearch @param {{title:string,description:string,submitLabel:string}} labels */
export function openVoice(dialog, onSearch, labels) {
  const lifecycle = new AbortController();
  const signal = lifecycle.signal;
  let recorder = null;
  let stream = null;
  let audio = null;
  let timer = null;
  let elapsed = null;
  let previewUrl = null;
  let closed = false;
  dialog.className = 'voice-modal';
  dialog.innerHTML = '<div class="dialog-top"><h2 id="dialog-title">'+esc(labels.title)+'</h2><button class="icon-button" data-action="close-modal" aria-label="Đóng">' + icon('close') + '</button></div>' +
    '<div class="voice-orb">' + icon('mic') + '</div><p class="center muted">'+esc(labels.description)+'</p>' +
    '<p class="voice-status center" id="voice-status" role="status">Sẵn sàng lắng nghe bạn</p>' +
    '<button id="record-audio" class="button primary full">' + icon('mic') + ' Bắt đầu ghi âm</button>' +
    '<label class="file-alternative">Hoặc chọn tệp âm thanh<input id="audio-file" type="file" accept="audio/webm,audio/mp4,audio/mpeg,audio/wav,audio/ogg"></label>' +
    '<audio id="audio-preview" controls hidden></audio><button id="transcribe-audio" class="button secondary full" hidden>Chuyển thành văn bản</button>' +
    '<form id="transcript-form" hidden><label class="field">Nội dung nhận được<input name="transcript" id="transcript" maxlength="2000" required></label><button class="button primary full" type="submit">'+esc(labels.submitLabel)+' ' + icon('arrow') + '</button></form>' +
    '<p class="form-error" id="voice-error" role="alert"></p><p class="fine-print center">' + icon('shield') + ' Âm thanh được gửi tới ElevenLabs khi bạn chọn chuyển thành văn bản. Ghi tối đa 30 giây; máy chủ không lưu bản ghi.</p>';
  dialog.showModal();

  const status = dialog.querySelector('#voice-status');
  const error = dialog.querySelector('#voice-error');
  const recordButton = dialog.querySelector('#record-audio');
  const transcribeButton = dialog.querySelector('#transcribe-audio');
  function stopTracks() {
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    clearTimeout(timer);
    clearInterval(elapsed);
  }
  function ready(blob) {
    if (closed) return;
    audio = blob;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(blob);
    const player = dialog.querySelector('#audio-preview');
    player.src = previewUrl;
    player.hidden = false;
    transcribeButton.hidden = false;
    recordButton.textContent = 'Ghi âm lại';
    recordButton.classList.remove('recording');
    status.textContent = 'Bản ghi đã sẵn sàng. Bạn có thể nghe lại trước khi gửi.';
  }
  recordButton.addEventListener('click', async () => {
    error.textContent = '';
    if (recorder?.state === 'recording') {
      recorder.stop();
      stopTracks();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      error.textContent = 'Trình duyệt chưa hỗ trợ ghi âm. Hãy tải tệp âm thanh hoặc dùng trình duyệt mới hơn.';
      return;
    }
    recordButton.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (closed) { stopTracks(); return; }
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
      const chunks = [];
      recorder.addEventListener('dataavailable', event => { if (event.data.size) chunks.push(event.data); });
      recorder.addEventListener('stop', () => ready(new Blob(chunks, { type: recorder.mimeType })), { once: true });
      recorder.start();
      recordButton.textContent = 'Dừng ghi âm';
      recordButton.classList.add('recording');
      let seconds = 0;
      status.textContent = 'Đang ghi âm · 0 / 30 giây';
      elapsed = setInterval(() => { seconds++; status.textContent = 'Đang ghi âm · ' + seconds + ' / 30 giây'; }, 1000);
      timer = setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); stopTracks(); }, 30000);
    } catch (err) {
      stopTracks();
      error.textContent = err.name === 'NotAllowedError' ? 'Chưa được phép dùng microphone. Hãy cấp quyền trong trình duyệt hoặc tải tệp âm thanh.' : 'Không mở được microphone: ' + err.message;
    } finally { recordButton.disabled = false; }
  }, { signal });
  dialog.querySelector('#audio-file').addEventListener('change', event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { error.textContent = 'Tệp âm thanh phải nhỏ hơn 10 MB.'; return; }
    if (recorder?.state === 'recording') recorder.stop();
    stopTracks();
    ready(file);
  }, { signal });
  transcribeButton.addEventListener('click', async () => {
    if (!audio) return;
    transcribeButton.disabled = true;
    recordButton.disabled = true;
    error.textContent = '';
    status.textContent = 'ElevenLabs đang chuyển giọng nói thành văn bản…';
    try {
      const result = await api('/search/transcribe', { method: 'POST', headers: { 'Content-Type': audio.type || 'audio/webm', 'X-Media-Consent':'true' }, body: audio, signal });
      dialog.querySelector('#transcript-form').hidden = false;
      dialog.querySelector('#transcript').value = result.text;
      dialog.querySelector('#transcript').focus();
      status.textContent = 'Đã nhận giọng nói. Kiểm tra hoặc sửa nội dung trước khi tìm.';
    } catch (err) {
      if (err.name !== 'AbortError') { error.textContent = err.message; status.textContent = 'Chưa thể nhận diện bản ghi.'; }
    } finally { transcribeButton.disabled = false; recordButton.disabled = false; }
  }, { signal });
  dialog.querySelector('#transcript-form').addEventListener('submit', event => {
    event.preventDefault();
    const text = dialog.querySelector('#transcript').value.trim();
    if (text) { dialog.close(); onSearch(text); }
  }, { signal });
  dialog.addEventListener('close', () => {
    closed = true;
    lifecycle.abort();
    if (recorder?.state === 'recording') recorder.stop();
    stopTracks();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, { once: true });
}
