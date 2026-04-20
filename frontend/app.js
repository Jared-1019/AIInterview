const { createApp } = Vue;

createApp({
  data() {
    return {
      input: '',
      conversation: [],
      isTyping: false,
      isRecording: false,
      voiceStatus: 'Ready',
      mediaStream: null,
      mediaRecorder: null,
      audioChunks: [],
      showActionMenu: false,
      showVoiceModal: false,
      voiceModalStatus: '请开始说话，2秒静默后自动结束。',
      callActive: false,
      isListening: false,
      isSpeaking: false,
      audioContext: null,
      analyserNode: null,
      processorNode: null,
      lastSpeechTime: 0,
      silenceThreshold: 0.02,
      silenceDelay: 2000,
      audioPlayBlocked: false,
      pendingAudio: null,
      playbackAudioContext: null,
      pendingPlaybackBuffer: null,
    };
  },
  methods: {
    async sendMessage() {
      const text = this.input.trim();
      if (!text) return;
      this.input = '';
      await this.submitMessage(text);
    },
    async submitMessage(text) {
      this.conversation.push({ role: 'user', text });
      this.isTyping = true;
      this.conversation.push({ role: 'assistant', text: '' });
      const assistantIndex = this.conversation.length - 1;
      this.$nextTick(this.scrollBottom);

      try {
        const resp = await fetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ message: text }),
        });

        if (!resp.ok) {
          throw new Error(`Server returned ${resp.status}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let partial = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          partial += decoder.decode(value, { stream: true });
          this.conversation[assistantIndex].text = partial;
          this.$nextTick(this.scrollBottom);
        }

        partial += decoder.decode();
        this.conversation[assistantIndex].text = partial;
      } catch (error) {
        this.conversation[assistantIndex].text = `Error: ${error.message}`;
      } finally {
        this.isTyping = false;
        this.$nextTick(this.scrollBottom);
      }
    },
    async toggleRecording() {
      if (this.isRecording) {
        this.stopRecording();
        return;
      }

      if (!navigator.mediaDevices || !window.MediaRecorder) {
        this.voiceStatus = 'Browser does not support audio recording.';
        return;
      }

      try {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.audioChunks = [];

        this.mediaRecorder = new MediaRecorder(this.mediaStream);

        this.mediaRecorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };

        this.mediaRecorder.onerror = (event) => {
          const message = event.error?.message || event.error || 'Recorder failed';
          this.voiceStatus = `Voice chat failed: ${message}`;
        };

        this.mediaRecorder.onstop = async () => {
          await this.processRecording();
        };

        this.mediaRecorder.start();
        this.isRecording = true;
        this.voiceStatus = 'Recording...';
      } catch (error) {
        this.voiceStatus = `Microphone denied: ${error.message}`;
      }
    },
    stopRecording() {
      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop();
      }
      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      }
      this.isRecording = false;
      this.voiceStatus = 'Processing audio...';
    },
    async processRecording() {
      try {
        if (!this.audioChunks.length) {
          throw new Error('No audio captured.');
        }

        const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
        const audioBlob = new Blob(this.audioChunks, { type: mimeType });

        this.voiceStatus = 'Uploading audio...';
        const formData = new FormData();
        formData.append('audio', audioBlob, 'voice-recording');
        const asrUrl = 'http://127.0.0.1:3001/api/asr';

        const asrResponse = await fetch(asrUrl, {
          method: 'POST',
          body: formData,
        });

        if (!asrResponse.ok) {
          throw new Error(`ASR server returned ${asrResponse.status}`);
        }

        const asrResult = await asrResponse.json();
        const transcript = asrResult.text?.trim() || '';

        if (!transcript) {
          this.voiceStatus = '未识别到语音，请重试。';
          return;
        }

        this.input = transcript;
        this.voiceStatus = '语音识别完成，已回填到文本框，可编辑后发送。';
      } catch (error) {
        this.voiceStatus = `Voice chat failed: ${error.message}`;
      } finally {
        this.audioChunks = [];
      }
    },
    scrollBottom() {
      const conversation = document.querySelector('.conversation');
      if (conversation) {
        conversation.scrollTop = conversation.scrollHeight;
      }
    },
    resizeTextarea(event) {
      const textarea = event.target;
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    },
    toggleActionMenu() {
      this.showActionMenu = !this.showActionMenu;
    },
    async openVoiceCall() {
      this.showActionMenu = false;
      this.showVoiceModal = true;
      this.callActive = true;
      this.voiceModalStatus = '请开始说话，2秒静默后自动结束。';
      await this.unlockPlayback();
      await this.startVoiceCall();
    },
    closeVoiceModal() {
      this.showVoiceModal = false;
      this.endVoiceCall('已结束通话');
    },
    async startVoiceCall() {
      if (!this.callActive) {
        return;
      }
      if (!navigator.mediaDevices || !window.MediaRecorder) {
        this.voiceModalStatus = '浏览器不支持录音';
        return;
      }

      try {
        this.isSpeaking = false;
        this.audioPlayBlocked = false;
        this.pendingPlaybackBuffer = null;
        this.pendingAudio = null;
        this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.audioChunks = [];

        this.mediaRecorder = new MediaRecorder(this.mediaStream);
        this.mediaRecorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };
        this.mediaRecorder.onerror = (event) => {
          const message = event.error?.message || event.error || 'Recorder failed';
          this.voiceModalStatus = `录音失败: ${message}`;
        };
        this.mediaRecorder.onstop = async () => {
          this.cleanupAudioContext();
          this.isListening = false;
          if (this.callActive) {
            await this.processVoiceCall();
          }
        };

        this.mediaRecorder.start();
        this.isListening = true;
        this.voiceModalStatus = 'AI 正在听，请开始说话；2秒静默后自动结束。';
        this.startSilenceMonitor();
      } catch (error) {
        this.voiceModalStatus = `麦克风权限被拒绝: ${error.message}`;
      }
    },
    stopVoiceCall(statusMessage = '录音已停止，处理中...', endCall = false) {
      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop();
      }
      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      }
      this.isListening = false;
      if (endCall) {
        this.callActive = false;
      }
      this.voiceModalStatus = statusMessage;
    },
    endVoiceCall(statusMessage = '通话已结束') {
      this.callActive = false;
      this.isListening = false;
      this.isSpeaking = false;
      this.audioPlayBlocked = false;
      if (this.pendingAudio) {
        try {
          this.pendingAudio.pause?.();
          this.pendingAudio.currentTime = 0;
        } catch (_e) {
          // ignore
        }
      }
      this.pendingAudio = null;
      this.pendingPlaybackBuffer = null;
      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop();
      }
      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      }
      this.voiceModalStatus = statusMessage;
    },
    async unlockPlayback() {
      if (this.playbackAudioContext) {
        if (this.playbackAudioContext.state === 'suspended') {
          try {
            await this.playbackAudioContext.resume();
          } catch (error) {
            console.warn('playbackAudioContext resume failed:', error);
          }
        }
        return;
      }

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) {
        return;
      }

      try {
        this.playbackAudioContext = new AudioContext();
        if (this.playbackAudioContext.state === 'suspended') {
          await this.playbackAudioContext.resume();
        }
      } catch (error) {
        console.warn('Unable to create playback AudioContext:', error);
        this.playbackAudioContext = null;
      }
    },
    base64ToArrayBuffer(base64) {
      const binaryString = window.atob(base64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i += 1) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      return bytes.buffer;
    },
    async resumePlayback() {
      if (this.pendingPlaybackBuffer && this.playbackAudioContext) {
        try {
          const source = this.playbackAudioContext.createBufferSource();
          source.buffer = this.pendingPlaybackBuffer;
          source.connect(this.playbackAudioContext.destination);
          source.onended = () => {
            this.isSpeaking = false;
            this.audioPlayBlocked = false;
            this.pendingPlaybackBuffer = null;
            if (this.callActive) {
              this.voiceModalStatus = 'AI 回复完成，请继续说话。';
              this.startVoiceCall();
            } else {
              this.voiceModalStatus = '语音通话结束';
            }
          };
          source.start(0);
          this.isSpeaking = true;
          this.audioPlayBlocked = false;
          this.voiceModalStatus = '正在播放 AI 回复';
        } catch (error) {
          this.voiceModalStatus = `播放失败: ${error.message}`;
          this.isSpeaking = false;
        }
        return;
      }

      if (!this.pendingAudio) return;
      try {
        this.pendingAudio.playbackRate = 1.5;
        this.pendingAudio.preservesPitch = true;
        this.pendingAudio.mozPreservesPitch = true;
        this.pendingAudio.webkitPreservesPitch = true;
        this.voiceModalStatus = '正在播放 AI 回复';
        this.isSpeaking = true;
        await this.pendingAudio.play();
        this.audioPlayBlocked = false;
      } catch (error) {
        this.voiceModalStatus = `播放失败: ${error.message}`;
        this.isSpeaking = false;
      }
    },
    startSilenceMonitor() {
      try {
        if (!this.mediaStream) return;
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyserNode = this.audioContext.createAnalyser();
        this.analyserNode.fftSize = 2048;
        source.connect(this.analyserNode);

        this.processorNode = this.audioContext.createScriptProcessor(2048, 1, 1);
        this.analyserNode.connect(this.processorNode);
        this.processorNode.connect(this.audioContext.destination);

        this.lastSpeechTime = performance.now();
        this.processorNode.onaudioprocess = () => {
          const data = new Uint8Array(this.analyserNode.fftSize);
          this.analyserNode.getByteTimeDomainData(data);
          let maxAmp = 0;
          for (let i = 0; i < data.length; i += 1) {
            const amp = Math.abs(data[i] - 128) / 128;
            if (amp > maxAmp) maxAmp = amp;
          }
          if (maxAmp > this.silenceThreshold) {
            this.lastSpeechTime = performance.now();
          } else if (performance.now() - this.lastSpeechTime > this.silenceDelay && this.isListening) {
            this.voiceModalStatus = '检测到静默，正在发送语音...';
            this.stopVoiceCall('检测到静默，正在发送语音...');
          }
        };
      } catch (error) {
        console.warn('Silence monitor failed:', error);
      }
    },
    cleanupAudioContext() {
      if (this.processorNode) {
        this.processorNode.disconnect();
        this.processorNode.onaudioprocess = null;
        this.processorNode = null;
      }
      if (this.analyserNode) {
        this.analyserNode.disconnect();
        this.analyserNode = null;
      }
      if (this.audioContext) {
        try {
          this.audioContext.close();
        } catch (_e) {
          // ignore
        }
        this.audioContext = null;
      }
    },
    async processVoiceCall() {
      try {
        const formData = new FormData();
        let phoneUrl = 'http://127.0.0.1:3003/api/phone';

        if (this.audioChunks.length) {
          const audioBlob = new Blob(this.audioChunks, { type: this.mediaRecorder?.mimeType || 'audio/webm' });
          formData.append('audio', audioBlob, 'voice-recording');
        } else {
          formData.append('silent', 'true');
        }

        const resp = await fetch(phoneUrl, {
          method: 'POST',
          body: formData,
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.error || `Server returned ${resp.status}`);
        }

        const result = await resp.json();
        const userText = result.input_text || '';
        const replyText = result.response_text || '';

        if (userText) {
          this.conversation.push({ role: 'user', text: userText });
        } else {
          this.conversation.push({ role: 'user', text: '（未检测到语音）' });
        }

        this.conversation.push({ role: 'assistant', text: replyText || 'AI 未返回任何文本。' });
        this.$nextTick(this.scrollBottom);

        if (result.audio_base64) {
          this.isSpeaking = true;
          this.isListening = false;
          this.voiceModalStatus = 'AI 已回复，正在播放语音';
          const audioData = this.base64ToArrayBuffer(result.audio_base64);
          if (this.playbackAudioContext) {
            try {
              const decoded = await this.playbackAudioContext.decodeAudioData(audioData.slice(0));
              const source = this.playbackAudioContext.createBufferSource();
              source.buffer = decoded;
              source.connect(this.playbackAudioContext.destination);
              source.onended = () => {
                this.isSpeaking = false;
                this.audioPlayBlocked = false;
                this.pendingPlaybackBuffer = null;
                if (this.callActive) {
                  this.voiceModalStatus = 'AI 回复完成，请继续说话。';
                  this.startVoiceCall();
                } else {
                  this.voiceModalStatus = '语音通话结束';
                }
              };
              source.start(0);
              this.audioPlayBlocked = false;
              this.pendingPlaybackBuffer = null;
            } catch (decodeError) {
              console.warn('AudioContext playback failed:', decodeError);
              this.pendingPlaybackBuffer = null;
              this.pendingAudio = new Audio(`data:audio/wav;base64,${result.audio_base64}`);
              this.pendingAudio.playbackRate = 1.5;
              this.pendingAudio.preservesPitch = true;
              this.pendingAudio.mozPreservesPitch = true;
              this.pendingAudio.webkitPreservesPitch = true;
              this.pendingAudio.onended = () => {
                this.isSpeaking = false;
                this.audioPlayBlocked = false;
                this.pendingAudio = null;
                if (this.callActive) {
                  this.voiceModalStatus = 'AI 回复完成，请继续说话。';
                  this.startVoiceCall();
                } else {
                  this.voiceModalStatus = '语音通话结束';
                }
              };
              try {
                await this.pendingAudio.play();
                this.audioPlayBlocked = false;
                this.pendingAudio = null;
              } catch (playError) {
                console.warn('Audio autoplay blocked:', playError);
                this.audioPlayBlocked = true;
                this.isSpeaking = false;
                this.voiceModalStatus = '自动播放被拦截，请点击播放按钮。';
              }
            }
          } else {
            const audio = new Audio(`data:audio/wav;base64,${result.audio_base64}`);
            audio.playbackRate = 1.5;
            audio.preservesPitch = true;
            audio.mozPreservesPitch = true;
            audio.webkitPreservesPitch = true;
            audio.onended = () => {
              this.isSpeaking = false;
              this.audioPlayBlocked = false;
              this.pendingAudio = null;
              if (this.callActive) {
                this.voiceModalStatus = 'AI 回复完成，请继续说话。';
                this.startVoiceCall();
              } else {
                this.voiceModalStatus = '语音通话结束';
              }
            };
            try {
              await audio.play();
              this.audioPlayBlocked = false;
              this.pendingAudio = null;
            } catch (playError) {
              console.warn('Audio autoplay blocked:', playError);
              audio.playbackRate = 1.5;
              audio.preservesPitch = true;
              audio.mozPreservesPitch = true;
              audio.webkitPreservesPitch = true;
              this.audioPlayBlocked = true;
              this.pendingAudio = audio;
              this.isSpeaking = false;
              this.voiceModalStatus = '自动播放被拦截，请点击播放按钮。';
            }
          }
        } else {
          this.voiceModalStatus = 'AI 回复完成，但未生成音频';
          if (this.callActive) {
            this.startVoiceCall();
          }
        }
      } catch (error) {
        this.voiceModalStatus = `语音聊天失败: ${error.message}`;
        this.isSpeaking = false;
      } finally {
        this.audioChunks = [];
      }
    },
  },
}).mount('#app');
