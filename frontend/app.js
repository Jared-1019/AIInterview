const { createApp } = Vue;

createApp({
  data() {
    return {
      input: '',
      conversation: [],
      isTyping: false,
    };
  },
  methods: {
    async sendMessage() {
      const text = this.input.trim();
      if (!text) return;

      this.conversation.push({ role: 'user', text });
      this.input = '';
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
  },
}).mount('#app');
