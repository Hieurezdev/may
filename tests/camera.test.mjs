import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { LiveCamera } from '../frontend/camera.js';

class Track extends EventTarget {
  stopped = 0;
  stop() { this.stopped++; }
}
class Video {
  srcObject = null;
  readyState = 2;
  paused = true;
  async play() { this.paused = false; }
  pause() { this.paused = true; }
}
const globals = new Map();
let frames;
let track;
let stream;
let media;
let nextFrame;
function setGlobal(name, value) {
  if (!globals.has(name)) globals.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
  Object.defineProperty(globalThis, name, { configurable: true, value });
}
beforeEach(() => {
  track = new Track();
  stream = { getTracks: () => [track], getVideoTracks: () => [track] };
  media = {
    getUserMedia: async () => stream,
    enumerateDevices: async () => [{kind:'videoinput'}, {kind:'videoinput'}],
  };
  frames = new Map();
  nextFrame = 1;
  setGlobal('isSecureContext', true);
  setGlobal('navigator', {mediaDevices: media});
  setGlobal('requestAnimationFrame', callback => { const id = nextFrame++; frames.set(id, callback); return id; });
  setGlobal('cancelAnimationFrame', id => frames.delete(id));
});
afterEach(() => {
  for (const [name, descriptor] of globals) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
  }
  globals.clear();
});

test('camera renders successive frames and stops all resources', async () => {
  let count = 0;
  const video = new Video();
  const camera = new LiveCamera(video, () => count++, () => {});
  assert.equal(await camera.start('user'), true);
  assert.equal(camera.active, true);
  assert.equal(video.srcObject, stream);
  for (let i = 0; i < 3; i++) {
    const [id, callback] = frames.entries().next().value;
    frames.delete(id);
    callback();
  }
  assert.equal(count, 3);
  assert.equal(frames.size, 1);
  camera.stop();
  assert.equal(track.stopped, 1);
  assert.equal(video.srcObject, null);
  assert.equal(video.paused, true);
  assert.equal(camera.active, false);
  assert.equal(frames.size, 0);
});

test('navigating away while permission is pending stops a later granted stream', async () => {
  let grant;
  media.getUserMedia = () => new Promise(resolve => { grant = resolve; });
  const video = new Video();
  const camera = new LiveCamera(video, () => {}, () => {});
  const pending = camera.start('user');
  camera.stop();
  grant(stream);
  assert.equal(await pending, false);
  assert.equal(track.stopped, 1);
  assert.equal(video.srcObject, null);
  assert.equal(frames.size, 0);
});

test('a newer camera request wins without reviving an old stream', async () => {
  const grants = [];
  media.getUserMedia = () => new Promise(resolve => grants.push(resolve));
  const camera = new LiveCamera(new Video(), () => {}, () => {});
  const first = camera.start('user');
  const second = camera.start('environment');
  const oldTrack = new Track();
  grants[1](stream);
  assert.equal(await second, true);
  grants[0]({getTracks:()=>[oldTrack],getVideoTracks:()=>[oldTrack]});
  assert.equal(await first, false);
  assert.equal(oldTrack.stopped, 1);
  assert.equal(track.stopped, 0);
  assert.equal(camera.active, true);
  camera.stop();
});

test('permission rejection leaves the camera stopped', async () => {
  media.getUserMedia = async () => { throw new DOMException('denied','NotAllowedError'); };
  const camera = new LiveCamera(new Video(), () => {}, () => {});
  await assert.rejects(camera.start('user'), /cấp quyền/);
  assert.equal(camera.active, false);
  assert.equal(frames.size, 0);
});

test('playback failure releases the acquired camera', async () => {
  const video = new Video();
  video.play = async () => { throw new Error('playback unavailable'); };
  const camera = new LiveCamera(video, () => {}, () => {});
  await assert.rejects(camera.start('user'), /playback unavailable/);
  assert.equal(track.stopped, 1);
  assert.equal(video.srcObject, null);
  assert.equal(frames.size, 0);
});

test('unplugged camera notifies the UI and cancels rendering', async () => {
  let ended = 0;
  const camera = new LiveCamera(new Video(), () => {}, () => ended++);
  await camera.start('user');
  track.dispatchEvent(new Event('ended'));
  track.dispatchEvent(new Event('ended'));
  assert.equal(ended, 1);
  assert.equal(camera.active, false);
  assert.equal(frames.size, 0);
});

test('insecure origin never requests camera permission', async () => {
  setGlobal('isSecureContext', false);
  let requested = false;
  media.getUserMedia = async () => { requested = true; return stream; };
  const camera = new LiveCamera(new Video(), () => {}, () => {});
  await assert.rejects(camera.start('user'), /HTTPS/);
  assert.equal(requested, false);
});
