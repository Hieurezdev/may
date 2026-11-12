(function() {
  'use strict';

  // Default configuration
  const DEFAULT_CONFIG = {
    theme: 'default',
    size: 'medium', 
    position: 'bottom-right',
    showBackground: true,
    domain: window.location.hostname,
    baseUrl: 'http://localhost:3000'
  };

  // Waifu AI Widget Class
  class WaifuWidget {
    constructor(config = {}) {
      this.config = { ...DEFAULT_CONFIG, ...config };
      this.baseUrl = this.config.baseUrl || 'http://localhost:3000';
      this.iframe = null;
      this.isVisible = true;
      this.init();
    }

    init() {
      this.createWidget();
      this.setupEventListeners();
    }

    createWidget() {
      // Create iframe container
      const container = document.createElement('div');
      container.id = 'waifu-ai-widget';
      container.style.cssText = this.getContainerStyles();

      // Create iframe
      this.iframe = document.createElement('iframe');
      this.iframe.src = this.buildIframeUrl();
      this.iframe.style.cssText = this.getIframeStyles();
      this.iframe.setAttribute('frameborder', '0');
      this.iframe.setAttribute('allow', 'microphone');

      // Create toggle button for fixed positions
      if (this.config.position.includes('bottom')) {
        const toggleBtn = this.createToggleButton();
        container.appendChild(toggleBtn);
      }

      container.appendChild(this.iframe);
      document.body.appendChild(container);
    }

    createToggleButton() {
      const button = document.createElement('button');
      button.innerHTML = '💬';
      button.style.cssText = `
        position: absolute;
        top: -40px;
        right: 0;
        background: #4F46E5;
        color: white;
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        cursor: pointer;
        font-size: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        transition: all 0.3s ease;
        z-index: 1000;
      `;

      button.addEventListener('click', () => this.toggle());
      
      button.addEventListener('mouseover', () => {
        button.style.background = '#3730A3';
        button.style.transform = 'scale(1.1)';
      });
      
      button.addEventListener('mouseout', () => {
        button.style.background = '#4F46E5';
        button.style.transform = 'scale(1)';
      });

      return button;
    }

    buildIframeUrl() {
      const params = new URLSearchParams({
        theme: this.config.theme,
        size: this.config.size,
        position: this.config.position,
        showBackground: this.config.showBackground.toString()
      });
      
      return `${this.baseUrl}/widget?${params.toString()}`;
    }

    getContainerStyles() {
      const baseStyles = `
        z-index: 10000;
        transition: all 0.3s ease;
        font-family: system-ui, -apple-system, sans-serif;
      `;

      const positionStyles = {
        'bottom-right': `
          position: fixed;
          bottom: 20px;
          right: 20px;
        `,
        'bottom-left': `
          position: fixed;
          bottom: 20px;
          left: 20px;
        `,
        'center': `
          position: relative;
          margin: 20px auto;
          display: flex;
          justify-content: center;
        `
      };

      return baseStyles + (positionStyles[this.config.position] || positionStyles['bottom-right']);
    }

    getIframeStyles() {
      const sizeStyles = {
        small: 'width: 320px; height: 400px;',
        medium: 'width: 384px; height: 500px;',
        large: 'width: 500px; height: 600px;'
      };

      return `
        border: none;
        border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        ${sizeStyles[this.config.size] || sizeStyles.medium}
      `;
    }

    setupEventListeners() {
      // Listen for messages from iframe
      window.addEventListener('message', (event) => {
        if (event.origin !== this.baseUrl.replace(/:\d+$/, '')) return;
        
        if (event.data.type === 'resize') {
          this.resize(event.data.width, event.data.height);
        }
      });
    }

    toggle() {
      this.isVisible = !this.isVisible;
      this.iframe.style.display = this.isVisible ? 'block' : 'none';
      
      const button = document.querySelector('#waifu-ai-widget button');
      if (button) {
        button.innerHTML = this.isVisible ? '💬' : '✨';
      }
    }

    resize(width, height) {
      if (width) this.iframe.style.width = width + 'px';
      if (height) this.iframe.style.height = height + 'px';
    }

    destroy() {
      const widget = document.getElementById('waifu-ai-widget');
      if (widget) {
        widget.remove();
      }
    }
  }

  // Global API
  window.WaifuAI = {
    // Create widget with config
    create: function(config) {
      return new WaifuWidget(config);
    },

    // Quick embed with minimal config
    embed: function(elementId, config = {}) {
      const element = document.getElementById(elementId);
      if (!element) {
        console.error('WaifuAI: Element not found:', elementId);
        return;
      }

      config.position = 'center';
      const widget = new WaifuWidget(config);
      
      // Move widget to target element
      const widgetElement = document.getElementById('waifu-ai-widget');
      element.appendChild(widgetElement);
      
      return widget;
    }
  };

  // Auto-initialize if data attributes are present
  document.addEventListener('DOMContentLoaded', function() {
    const autoInit = document.querySelector('[data-waifu-ai]');
    if (autoInit) {
      const config = {
        theme: autoInit.dataset.theme || 'default',
        size: autoInit.dataset.size || 'medium',
        position: autoInit.dataset.position || 'bottom-right',
        showBackground: autoInit.dataset.showBackground !== 'false',
        baseUrl: autoInit.dataset.baseUrl || 'http://localhost:3000'
      };
      
      window.WaifuAI.create(config);
    }
  });

})();
