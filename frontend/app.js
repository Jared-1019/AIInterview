const { createApp } = Vue;

createApp({
  data() {
    return {
      activeTab: 'chat',
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
      overallScore: 85,
      contentAnalysis: {
        technical: 88,
        depth: 82,
        logic: 86,
        match: 84,
        analysis: '您的技术回答整体正确，对核心概念有较好的理解。在知识深度方面，能够回答基本问题，但对于一些高级概念的理解还需加强。逻辑表达清晰，能够有条理地阐述观点。与岗位的匹配度较高，具备基本的技能要求。'
      },
      expressionAnalysis: {
        speechRate: '适中',
        clarity: '良好',
        confidence: '较高',
        analysis: '您的语速适中，表达清晰，能够让面试官清楚地理解您的观点。自信度较高，展现出良好的沟通能力。建议在回答复杂问题时，可以适当放慢语速，确保表达更加精准。'
      },
      suggestions: [
        '加强对高级技术概念的学习，特别是与岗位相关的前沿技术',
        '在回答问题时，可以采用STAR法则（情境、任务、行动、结果）来结构化回答',
        '多练习技术问题的口头表达，提高语言组织能力',
        '增加项目经验的描述，突出自己在项目中的贡献和成果',
        '关注行业动态，了解最新的技术趋势和发展方向'
      ],
      interviewHistory: [
        {
          date: '2026-04-20',
          score: 82,
          role: '前端开发工程师',
          summary: '第一次模拟面试，技术基础扎实，但表达能力有待提高。'
        },
        {
          date: '2026-04-15',
          score: 78,
          role: '前端开发工程师',
          summary: '技术问题回答基本正确，但对框架原理理解不够深入。'
        },
        {
          date: '2026-04-10',
          score: 75,
          role: '前端开发工程师',
          summary: '初次面试，紧张导致表达不流畅，技术知识点掌握不够全面。'
        }
      ],
      // 面试相关状态
      interviewState: 'idle', // idle, selecting_position, questions_generated, formal_interview
      position: '',
      showQuestions: false,
      questions: [],
      currentQuestionIndex: 0,
      questionsLoaded: 0
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
        // 分析用户回答，提取关键词，生成智能追问
        const followUpQuestion = this.generateFollowUpQuestion(text);
        
        let responseText = '';
        if (followUpQuestion) {
          responseText = followUpQuestion;
        } else {
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

          responseText = partial + decoder.decode();
        }
        
        this.conversation[assistantIndex].text = responseText;
      } catch (error) {
        this.conversation[assistantIndex].text = `Error: ${error.message}`;
      } finally {
        this.isTyping = false;
        this.$nextTick(this.scrollBottom);
      }
    },
    generateFollowUpQuestion(text) {
      // 模拟智能追问逻辑，根据用户回答的关键词生成追问
      const lowerText = text.toLowerCase();
      
      // 技术相关关键词
      const techKeywords = {
        'javascript': ['您能详细说明一下您对JavaScript的理解吗？', '您在项目中使用JavaScript解决过哪些复杂问题？', '您对ES6及以上版本的新特性有哪些了解？'],
        'react': ['您使用React开发过哪些项目？', '您如何理解React的虚拟DOM？', '您在React项目中如何处理状态管理？'],
        'vue': ['您使用Vue开发过哪些项目？', '您如何理解Vue的响应式原理？', '您在Vue项目中如何处理组件通信？'],
        'angular': ['您使用Angular开发过哪些项目？', '您如何理解Angular的依赖注入？', '您在Angular项目中如何处理路由？'],
        'node.js': ['您使用Node.js开发过哪些后端服务？', '您如何处理Node.js的异步操作？', '您在Node.js项目中如何优化性能？'],
        'typescript': ['您使用TypeScript开发过哪些项目？', '您如何理解TypeScript的类型系统？', '您在TypeScript项目中如何处理类型定义？'],
        'html': ['您如何理解HTML5的新特性？', '您在项目中如何优化HTML结构？', '您如何处理HTML的语义化？'],
        'css': ['您如何理解CSS3的新特性？', '您在项目中如何优化CSS代码？', '您如何处理CSS的响应式设计？'],
        'webpack': ['您在项目中如何配置Webpack？', '您如何优化Webpack的构建性能？', '您对Webpack的工作原理有哪些了解？'],
        'git': ['您在项目中如何使用Git进行版本控制？', '您如何处理Git的分支管理？', '您如何解决Git的冲突？'],
      };
      
      // 项目经验相关关键词
      const projectKeywords = {
        '项目': ['您能详细描述一下您参与的最具挑战性的项目吗？', '您在项目中担任什么角色？', '您如何解决项目中遇到的技术难题？'],
        '经验': ['您有多少年的前端开发经验？', '您在前端开发中积累了哪些宝贵的经验？', '您如何不断提升自己的前端开发技能？'],
        '团队': ['您如何与团队成员协作开发？', '您在团队中如何解决技术分歧？', '您如何处理团队中的沟通问题？'],
      };
      
      // 软技能相关关键词
      const softSkillsKeywords = {
        '沟通': ['您如何与非技术人员沟通技术问题？', '您如何向团队成员解释复杂的技术概念？', '您如何处理工作中的反馈和批评？'],
        '学习': ['您如何保持对前端技术的学习？', '您最近学习了哪些新的前端技术？', '您如何将新学到的技术应用到实际项目中？'],
        '问题解决': ['您如何解决工作中遇到的技术问题？', '您如何处理项目中的紧急情况？', '您如何优化自己的问题解决能力？'],
      };
      
      // 检查技术关键词
      for (const [keyword, questions] of Object.entries(techKeywords)) {
        if (lowerText.includes(keyword)) {
          return questions[Math.floor(Math.random() * questions.length)];
        }
      }
      
      // 检查项目经验关键词
      for (const [keyword, questions] of Object.entries(projectKeywords)) {
        if (lowerText.includes(keyword)) {
          return questions[Math.floor(Math.random() * questions.length)];
        }
      }
      
      // 检查软技能关键词
      for (const [keyword, questions] of Object.entries(softSkillsKeywords)) {
        if (lowerText.includes(keyword)) {
          return questions[Math.floor(Math.random() * questions.length)];
        }
      }
      
      // 如果没有匹配的关键词，返回null，使用默认的LLM响应
      return null;
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
    startInterview() {
      this.showActionMenu = false;
      this.conversation = [];
      this.conversation.push({ 
        role: 'assistant', 
        text: '你好，欢迎来到AI interview助手，请选择你的目标岗位' 
      });
      this.$nextTick(this.scrollBottom);
      this.interviewState = 'selecting_position';
      this.showQuestions = false;
      this.questions = [];
    },
    async submitMessage(text) {
      this.conversation.push({ role: 'user', text });
      this.isTyping = true;
      this.conversation.push({ role: 'assistant', text: '' });
      const assistantIndex = this.conversation.length - 1;
      this.$nextTick(this.scrollBottom);

      try {
        // 处理面试状态
        if (this.interviewState === 'selecting_position') {
          // 用户选择了岗位
          this.position = text;
          this.conversation[assistantIndex].text = '正在为你生成面试题目，请稍候';
          this.$nextTick(this.scrollBottom);
          
          // 模拟生成题目
          setTimeout(() => {
            this.generateInterviewQuestions();
            this.isTyping = false;
          }, 2000);
        } else {
          // 分析用户回答，提取关键词，生成智能追问
          const followUpQuestion = this.generateFollowUpQuestion(text);
          
          let responseText = '';
          if (followUpQuestion) {
            responseText = followUpQuestion;
          } else {
            // 根据面试状态选择不同的API
            const apiUrl = this.interviewState === 'formal_interview' ? '/api/interview-chat' : '/api/chat';
            const requestBody = this.interviewState === 'formal_interview' 
              ? { message: text, position: this.position } 
              : { message: text };
            
            const resp = await fetch(apiUrl, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify(requestBody),
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

            responseText = partial + decoder.decode();
          }
          
          this.conversation[assistantIndex].text = responseText;
          this.isTyping = false;
          this.$nextTick(this.scrollBottom);
        }
      } catch (error) {
        this.conversation[assistantIndex].text = `Error: ${error.message}`;
        this.isTyping = false;
        this.$nextTick(this.scrollBottom);
      }
    },
    async generateInterviewQuestions() {
      // 清空题目数组
      this.questions = [];
      this.questionsLoaded = 0;
      
      // 显示题目区域
      this.showQuestions = true;
      
      try {
        // 构建提示词，让AI扮演面试官生成面试题目
        const prompt = `你是一个专业的${this.position}岗位面试官。现在有人来面试这个岗位，请生成10道面试题目，难度递增。

要求：
1. 题目要涵盖该岗位的核心技能、专业知识和实际工作场景
2. 题目难度从简单到困难递增（简单2道、中等4道、困难4道）
3. 每道题目需要标明难度等级（简单、中等、困难）
4. 题目要具体、有针对性，符合真实面试场景
5. 输出格式为JSON数组，包含10个对象，每个对象包含id、difficulty、question三个字段

请直接输出JSON格式，不要包含其他解释性文字。`;

        // 调用后端API生成题目
        const response = await fetch('/api/generate-questions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ position: this.position, prompt: prompt }),
        });
        
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        
        const data = await response.json();
        const allQuestions = JSON.parse(data);
        
        // 模拟题目加载过程
        const loadQuestion = (index) => {
          if (index < allQuestions.length) {
            setTimeout(() => {
              this.questions.push(allQuestions[index]);
              this.questionsLoaded++;
              loadQuestion(index + 1);
            }, 500); // 每个题目加载间隔500ms
          } else {
            // 所有题目加载完成
            this.interviewState = 'questions_generated';
          }
        };
        
        // 开始加载题目
        loadQuestion(0);
      } catch (error) {
        console.error('Error generating questions:', error);
        // 生成失败时使用默认题目
        this.useDefaultQuestions();
      }
    },
    useDefaultQuestions() {
      // 默认题目，当API调用失败时使用
      const allQuestions = [
        {
          id: 1,
          difficulty: '简单',
          question: '请介绍一下你自己。'
        },
        {
          id: 2,
          difficulty: '简单',
          question: '你为什么选择我们公司？'
        },
        {
          id: 3,
          difficulty: '中等',
          question: '请描述一个你在工作中遇到的挑战，以及你是如何解决的。'
        },
        {
          id: 4,
          difficulty: '中等',
          question: '你对我们公司的产品有什么了解？'
        },
        {
          id: 5,
          difficulty: '中等',
          question: '你未来5年的职业规划是什么？'
        },
        {
          id: 6,
          difficulty: '困难',
          question: '请描述一个你主导的项目，以及你在其中的角色。'
        },
        {
          id: 7,
          difficulty: '困难',
          question: '你如何处理工作中的压力和挑战？'
        },
        {
          id: 8,
          difficulty: '困难',
          question: '你对团队合作有什么看法？'
        },
        {
          id: 9,
          difficulty: '困难',
          question: '你如何看待行业的未来发展？'
        },
        {
          id: 10,
          difficulty: '困难',
          question: '你有什么问题要问我们？'
        }
      ];
      
      // 模拟题目加载过程
      const loadQuestion = (index) => {
        if (index < allQuestions.length) {
          setTimeout(() => {
            this.questions.push(allQuestions[index]);
            this.questionsLoaded++;
            loadQuestion(index + 1);
          }, 500);
        } else {
          this.interviewState = 'questions_generated';
        }
      };
      
      loadQuestion(0);
    },
    startFormalInterview() {
      // 开始正式面试
      this.interviewState = 'formal_interview';
      this.conversation.push({ 
        role: 'assistant', 
        text: '好的，我们开始面试。' 
      });
      this.$nextTick(this.scrollBottom);
      
      // 构建面试官提示词，让AI扮演面试官从自我介绍开始引导
      const interviewPrompt = `你是一个专业的${this.position}岗位面试官。你已经准备好了对这个面试者的10道面试题目。

现在请按照以下规则进行面试：
1. 首先请面试者做自我介绍
2. 根据面试者的自我介绍内容，进行简单的交流和追问（控制在3次问答以内）
3. 3次问答后，自然过渡到面试题目的提问

请以面试官的身份，热情、专业地开始这场面试。
请直接开始，不需要等待面试者确认。`;
      
      // 调用面试聊天API，传递提示词
      this.callInterviewAPI(interviewPrompt);
      this.currentQuestionIndex = 0;
    },
    async callInterviewAPI(firstPrompt) {
      this.isTyping = true;
      this.conversation.push({ role: 'assistant', text: '' });
      const assistantIndex = this.conversation.length - 1;
      this.$nextTick(this.scrollBottom);
      
      try {
        const resp = await fetch('/api/interview-chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ 
            message: firstPrompt,
            position: this.position,
            isFirstMessage: true
          }),
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

        this.conversation[assistantIndex].text = partial;
      } catch (error) {
        this.conversation[assistantIndex].text = `Error: ${error.message}`;
      } finally {
        this.isTyping = false;
        this.$nextTick(this.scrollBottom);
      }
    },
    async analyzeInterview() {
      this.isTyping = true;
      // 模拟分析过程
      setTimeout(() => {
        this.isTyping = false;
        // 生成随机分数，模拟分析结果
        this.overallScore = Math.floor(Math.random() * 10) + 80;
        this.contentAnalysis = {
          technical: Math.floor(Math.random() * 15) + 75,
          depth: Math.floor(Math.random() * 15) + 75,
          logic: Math.floor(Math.random() * 15) + 75,
          match: Math.floor(Math.random() * 15) + 75,
          analysis: '您的技术回答整体正确，对核心概念有较好的理解。在知识深度方面，能够回答基本问题，但对于一些高级概念的理解还需加强。逻辑表达清晰，能够有条理地阐述观点。与岗位的匹配度较高，具备基本的技能要求。'
        };
        
        // 模拟情感分析结果
        const speechRateOptions = ['过快', '适中', '过慢'];
        const clarityOptions = ['良好', '一般', '较差'];
        const confidenceOptions = ['较高', '一般', '较低'];
        
        const speechRate = speechRateOptions[Math.floor(Math.random() * 3)];
        const clarity = clarityOptions[Math.floor(Math.random() * 3)];
        const confidence = confidenceOptions[Math.floor(Math.random() * 3)];
        
        let expressionAnalysisText = '';
        if (speechRate === '适中' && clarity === '良好' && confidence === '较高') {
          expressionAnalysisText = '您的语速适中，表达清晰，能够让面试官清楚地理解您的观点。自信度较高，展现出良好的沟通能力。建议在回答复杂问题时，可以适当放慢语速，确保表达更加精准。';
        } else if (speechRate === '过快') {
          expressionAnalysisText = '您的语速较快，可能会影响面试官对您回答的理解。建议适当放慢语速，确保每个观点都能清晰表达。同时，注意保持表达的清晰度和自信度。';
        } else if (speechRate === '过慢') {
          expressionAnalysisText = '您的语速较慢，可能会让面试官觉得您对问题的理解不够深入。建议适当加快语速，同时保持表达的清晰度和逻辑连贯性。';
        } else if (clarity === '较差') {
          expressionAnalysisText = '您的表达清晰度有待提高，可能会影响面试官对您回答的理解。建议在回答问题时，注意发音清晰，逻辑连贯，避免使用模糊的表达方式。';
        } else if (confidence === '较低') {
          expressionAnalysisText = '您的自信度较低，可能会影响面试官对您能力的评估。建议在回答问题时，保持自信的态度，声音洪亮，表达流畅，展现出自己的专业能力。';
        } else {
          expressionAnalysisText = '您的表达能力整体良好，但仍有提升空间。建议在回答问题时，注意语速适中，表达清晰，保持自信的态度，展现出自己的专业能力。';
        }
        
        this.expressionAnalysis = {
          speechRate: speechRate,
          clarity: clarity,
          confidence: confidence,
          analysis: expressionAnalysisText
        };
      }, 1500);
    },
    mounted() {
      // 初始化成长曲线图表
      this.initGrowthChart();
    },
    initGrowthChart() {
      // 使用Chart.js初始化成长曲线图表
      const ctx = document.getElementById('growthChart');
      if (ctx) {
        // 准备数据
        const labels = this.interviewHistory.map(item => item.date).reverse();
        const scores = this.interviewHistory.map(item => item.score).reverse();
        
        new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: '面试得分',
              data: scores,
              borderColor: '#7c3aed',
              backgroundColor: 'rgba(124, 58, 237, 0.1)',
              tension: 0.4,
              fill: true
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: false,
                min: 60,
                max: 100,
                grid: {
                  color: 'rgba(255, 255, 255, 0.1)'
                },
                ticks: {
                  color: 'rgba(255, 255, 255, 0.7)'
                }
              },
              x: {
                grid: {
                  color: 'rgba(255, 255, 255, 0.1)'
                },
                ticks: {
                  color: 'rgba(255, 255, 255, 0.7)'
                }
              }
            },
            plugins: {
              legend: {
                labels: {
                  color: 'rgba(255, 255, 255, 0.7)'
                }
              }
            }
          }
        });
      }
    }
  },
}).mount('#app');
