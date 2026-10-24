/**
 * AudioSplit Pro - Professional Audio Workstation Client
 * Modern Vanilla JavaScript with Real Waveform Visualization & Streaming Progress
 */

(function () {
  'use strict';

  // API Base URL Resolution
  const API_BASE = (window.location.port === '8000' || window.location.port === '')
    ? ''
    : (window.API_BASE_URL || 'http://localhost:8000');

  // Application State
  const state = {
    jobId: null,
    audioMetadata: null,
    currentFile: null,
    splitDurationMinutes: 30.0,
    isCustomDuration: false,
    pollTimer: null,
    isProcessing: false,
    maxUploadSizeBytes: 500 * 1024 * 1024 // 500 MB
  };

  // DOM Elements (Strict Preservation of Existing Selectors)
  const elements = {
    // Nav
    navToggle: document.getElementById('navToggle'),
    navMenu: document.getElementById('navMenu'),

    // Alerts
    globalErrorAlert: document.getElementById('globalErrorAlert'),
    errorTitle: document.getElementById('errorTitle'),
    errorMessage: document.getElementById('errorMessage'),
    errorCloseBtn: document.getElementById('errorCloseBtn'),

    // Cards / Panels
    uploadCard: document.getElementById('uploadCard'),
    settingsCard: document.getElementById('settingsCard'),
    processingCard: document.getElementById('processingCard'),
    resultsCard: document.getElementById('resultsCard'),

    // Upload Elements
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('audioFileInput'),
    browseBtn: document.getElementById('browseBtn'),
    uploadProgressContainer: document.getElementById('uploadProgressContainer'),
    uploadingFileName: document.getElementById('uploadingFileName'),
    uploadPercentage: document.getElementById('uploadPercentage'),
    uploadProgressFill: document.getElementById('uploadProgressFill'),
    uploadStatusSubtext: document.getElementById('uploadStatusSubtext'),

    // Metadata Display
    metaFilename: document.getElementById('metaFilename'),
    metaDuration: document.getElementById('metaDuration'),
    metaSize: document.getElementById('metaSize'),
    metaCodec: document.getElementById('metaCodec'),
    metaSampleRate: document.getElementById('metaSampleRate'),
    metaChannelsBitrate: document.getElementById('metaChannelsBitrate'),
    videoNotice: document.getElementById('videoNotice'),
    resetFileBtn: document.getElementById('resetFileBtn'),

    // Split Settings
    presetButtons: document.querySelectorAll('.preset-btn'),
    customDurationBox: document.getElementById('customDurationBox'),
    customMinutesInput: document.getElementById('customMinutesInput'),
    estSegmentsCount: document.getElementById('estSegmentsCount'),
    estSegmentsDetails: document.getElementById('estSegmentsDetails'),
    startSplitBtn: document.getElementById('startSplitBtn'),

    // Processing Display
    processingStatusTitle: document.getElementById('processingStatusTitle'),
    processingStatusMessage: document.getElementById('processingStatusMessage'),
    jobProgressFill: document.getElementById('jobProgressFill'),
    jobSegmentCounter: document.getElementById('jobSegmentCounter'),
    jobProgressPercent: document.getElementById('jobProgressPercent'),

    // Results Display
    resultsSubtitle: document.getElementById('resultsSubtitle'),
    zipSizeDisplay: document.getElementById('zipSizeDisplay'),
    downloadZipBtn: document.getElementById('downloadZipBtn'),
    segmentsList: document.getElementById('segmentsList'),
    splitAnotherBtn: document.getElementById('splitAnotherBtn'),

    // Workstation Chrome Elements
    currentProjectBadge: document.getElementById('currentProjectBadge'),
    sessionStatusPill: document.getElementById('sessionStatusPill'),
    helpBtn: document.getElementById('helpBtn'),
    helpModal: document.getElementById('helpModal'),
    closeHelpBtn: document.getElementById('closeHelpBtn'),
    projectsTableBody: document.getElementById('projectsTableBody'),
    historyLogBox: document.getElementById('historyLogBox'),

    // Waveform Elements
    waveformCanvas: document.getElementById('waveformCanvas'),
    waveformCanvasContainer: document.getElementById('waveformCanvasContainer'),
    waveformPlayhead: document.getElementById('waveformPlayhead'),
    waveformCutsOverlay: document.getElementById('waveformCutsOverlay'),
    waveformTimelineRuler: document.getElementById('waveformTimelineRuler'),
    waveformPlayBtn: document.getElementById('waveformPlayBtn'),
    waveformTimeDisplay: document.getElementById('waveformTimeDisplay'),
    playBtnLabel: document.getElementById('playBtnLabel')
  };

  // Waveform & Audio Preview Controller
  const waveformController = {
    audioElement: null,
    audioUrl: null,
    audioContext: null,
    isPlaying: false,
    durationSeconds: 0,
    animFrame: null,

    init() {
      if (elements.waveformPlayBtn) {
        elements.waveformPlayBtn.addEventListener('click', () => this.togglePlayback());
      }
      if (elements.waveformCanvasContainer) {
        elements.waveformCanvasContainer.addEventListener('click', (e) => this.handleSeek(e));
      }
    },

    async loadFile(file, metadata) {
      this.reset();
      this.durationSeconds = metadata.duration_seconds || 0;

      // Create preview audio element
      try {
        this.audioUrl = URL.createObjectURL(file);
        this.audioElement = new Audio(this.audioUrl);
        this.audioElement.addEventListener('timeupdate', () => this.onTimeUpdate());
        this.audioElement.addEventListener('ended', () => this.onPlaybackEnded());
      } catch (err) {
        console.warn('Preview audio creation bypassed:', err);
      }

      this.updateTimeDisplay(0, this.durationSeconds);
      this.updateRuler(this.durationSeconds);

      // Render actual waveform
      await this.drawWaveform(file, metadata);
    },

    async drawWaveform(file, metadata) {
      const canvas = elements.waveformCanvas;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const width = canvas.width;
      const height = canvas.height;

      ctx.clearRect(0, 0, width, height);

      // Background graph grid
      ctx.fillStyle = '#0B0F17';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = 'rgba(37, 48, 69, 0.5)';
      ctx.lineWidth = 1;

      // Horizontal centerline
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();

      // Attempt to decode actual audio PCM data
      let peaks = null;
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx && file.size < 40 * 1024 * 1024) { // decode up to 40 MB directly
          if (!this.audioContext) this.audioContext = new AudioCtx();
          const arrayBuffer = await file.slice(0, 15 * 1024 * 1024).arrayBuffer();
          const decoded = await this.audioContext.decodeAudioData(arrayBuffer);
          const channelData = decoded.getChannelData(0);
          peaks = this.extractPeaks(channelData, 220);
        }
      } catch (_) {
        // Fallback to algorithmic waveform envelope based on metadata
      }

      if (!peaks) {
        peaks = this.generateEnvelope(metadata, 220);
      }

      // Draw peak bars
      const numBars = peaks.length;
      const barWidth = Math.max(2, (width / numBars) - 1.5);
      const gradient = ctx.createLinearGradient(0, 0, 0, height);
      gradient.addColorStop(0, '#00D9FF');
      gradient.addColorStop(0.5, '#67E8F9');
      gradient.addColorStop(1, '#6366F1');

      ctx.fillStyle = gradient;

      for (let i = 0; i < numBars; i++) {
        const x = (i / numBars) * width;
        const peak = Math.max(0.08, Math.min(0.95, peaks[i]));
        const barHeight = peak * (height - 16);
        const y = (height - barHeight) / 2;

        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, 2);
        ctx.fill();
      }
    },

    extractPeaks(channelData, count) {
      const step = Math.floor(channelData.length / count);
      const peaks = [];
      for (let i = 0; i < count; i++) {
        let max = 0;
        const start = i * step;
        const end = Math.min(channelData.length, start + step);
        for (let j = start; j < end; j += 4) {
          const val = Math.abs(channelData[j]);
          if (val > max) max = val;
        }
        peaks.push(max);
      }
      return peaks;
    },

    generateEnvelope(metadata, count) {
      const peaks = [];
      const seed = (metadata.duration_seconds || 100) + (metadata.size_bytes || 500);
      for (let i = 0; i < count; i++) {
        const sin1 = Math.sin((i / 8) + seed);
        const sin2 = Math.cos((i / 18) * 1.5);
        const noise = ((i * 19) % 23) / 45;
        const val = Math.abs(sin1 * 0.4 + sin2 * 0.35 + noise * 0.25);
        peaks.push(val);
      }
      return peaks;
    },

    updateSplitMarkers(totalSeconds, splitMinutes) {
      if (!elements.waveformCutsOverlay || !totalSeconds || totalSeconds <= 0 || !splitMinutes) {
        if (elements.waveformCutsOverlay) elements.waveformCutsOverlay.innerHTML = '';
        return;
      }

      const splitSeconds = splitMinutes * 60;
      const count = Math.ceil(totalSeconds / splitSeconds);
      elements.waveformCutsOverlay.innerHTML = '';

      if (count <= 1) return;

      for (let i = 1; i < count; i++) {
        const cutTime = i * splitSeconds;
        if (cutTime >= totalSeconds) break;
        const pct = (cutTime / totalSeconds) * 100;

        const cutEl = document.createElement('div');
        cutEl.className = 'waveform-cut-line';
        cutEl.style.left = `${pct}%`;
        cutEl.innerHTML = `<span class="waveform-cut-tag font-mono">Cut ${i} (${Math.round(cutTime / 60)}m)</span>`;
        elements.waveformCutsOverlay.appendChild(cutEl);
      }
    },

    updateRuler(totalSeconds) {
      if (!elements.waveformTimelineRuler || !totalSeconds) return;
      elements.waveformTimelineRuler.innerHTML = '';
      const intervals = 6;
      for (let i = 0; i <= intervals; i++) {
        const sec = (totalSeconds / intervals) * i;
        const span = document.createElement('span');
        span.textContent = this.formatSeconds(sec);
        elements.waveformTimelineRuler.appendChild(span);
      }
    },

    togglePlayback() {
      if (!this.audioElement) return;
      if (this.isPlaying) {
        this.audioElement.pause();
        this.isPlaying = false;
        if (elements.playBtnLabel) elements.playBtnLabel.textContent = 'Preview';
      } else {
        this.audioElement.play().then(() => {
          this.isPlaying = true;
          if (elements.playBtnLabel) elements.playBtnLabel.textContent = 'Pause';
        }).catch(() => {});
      }
    },

    onTimeUpdate() {
      if (!this.audioElement) return;
      const cur = this.audioElement.currentTime;
      const dur = this.audioElement.duration || this.durationSeconds;
      this.updateTimeDisplay(cur, dur);

      if (elements.waveformPlayhead && dur > 0) {
        const pct = (cur / dur) * 100;
        elements.waveformPlayhead.style.left = `${pct}%`;
      }
    },

    onPlaybackEnded() {
      this.isPlaying = false;
      if (elements.playBtnLabel) elements.playBtnLabel.textContent = 'Preview';
      if (elements.waveformPlayhead) elements.waveformPlayhead.style.left = '0%';
    },

    handleSeek(e) {
      if (!this.audioElement || !this.durationSeconds) return;
      const rect = elements.waveformCanvasContainer.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const pct = Math.max(0, Math.min(1, clickX / rect.width));
      const seekTime = pct * this.durationSeconds;
      this.audioElement.currentTime = seekTime;
      this.onTimeUpdate();
    },

    updateTimeDisplay(current, total) {
      if (elements.waveformTimeDisplay) {
        elements.waveformTimeDisplay.textContent = `${this.formatSeconds(current)} / ${this.formatSeconds(total)}`;
      }
    },

    formatSeconds(s) {
      if (!s || isNaN(s)) return '00:00:00';
      const hrs = Math.floor(s / 3600);
      const mins = Math.floor((s % 3600) / 60);
      const secs = Math.floor(s % 60);
      return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    },

    reset() {
      if (this.audioElement) {
        this.audioElement.pause();
        this.audioElement = null;
      }
      if (this.audioUrl) {
        URL.revokeObjectURL(this.audioUrl);
        this.audioUrl = null;
      }
      this.isPlaying = false;
      if (elements.playBtnLabel) elements.playBtnLabel.textContent = 'Preview';
      if (elements.waveformPlayhead) elements.waveformPlayhead.style.left = '0%';
      if (elements.waveformCutsOverlay) elements.waveformCutsOverlay.innerHTML = '';
      if (elements.waveformCanvas) {
        const ctx = elements.waveformCanvas.getContext('2d');
        ctx.clearRect(0, 0, elements.waveformCanvas.width, elements.waveformCanvas.height);
      }
      this.updateTimeDisplay(0, 0);
    }
  };

  // Initialize
  function init() {
    setupNavigation();
    setupDropzone();
    setupSplitControls();
    setupActions();
    setupWorkstationTabs();
    setupHelpModal();
    waveformController.init();
    updateEstimator();

    const currentYearEl = document.getElementById('currentYear');
    if (currentYearEl) {
      currentYearEl.textContent = new Date().getFullYear();
    }
  }

  // Workstation Tab Navigation (Studio, Projects, History, Formats, Settings)
  function setupWorkstationTabs() {
    const tabButtons = document.querySelectorAll('.sidebar-item, .nav-link[data-view]');
    const views = {
      studio: document.getElementById('viewStudio'),
      projects: document.getElementById('viewProjects'),
      history: document.getElementById('viewHistory'),
      formats: document.getElementById('viewFormats'),
      settings: document.getElementById('viewSettings')
    };

    function switchView(targetViewKey) {
      if (!views[targetViewKey]) return;

      // Update active state on all buttons
      tabButtons.forEach(btn => {
        const viewKey = btn.getAttribute('data-view');
        if (viewKey === targetViewKey) {
          btn.classList.add('active');
          btn.setAttribute('aria-selected', 'true');
        } else {
          btn.classList.remove('active');
          btn.setAttribute('aria-selected', 'false');
        }
      });

      // Show target view, hide others
      Object.keys(views).forEach(key => {
        if (views[key]) {
          if (key === targetViewKey) {
            views[key].classList.remove('hidden');
            views[key].classList.add('active');
          } else {
            views[key].classList.add('hidden');
            views[key].classList.remove('active');
          }
        }
      });
    }

    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const viewKey = btn.getAttribute('data-view');
        if (viewKey) {
          e.preventDefault();
          switchView(viewKey);
        }
      });
    });
  }

  // Help & Shortcuts Modal Handler
  function setupHelpModal() {
    if (elements.helpBtn && elements.helpModal) {
      elements.helpBtn.addEventListener('click', () => {
        elements.helpModal.classList.remove('hidden');
      });
    }

    if (elements.closeHelpBtn && elements.helpModal) {
      elements.closeHelpBtn.addEventListener('click', () => {
        elements.helpModal.classList.add('hidden');
      });
    }

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && elements.helpModal && !elements.helpModal.classList.contains('hidden')) {
        elements.helpModal.classList.add('hidden');
      }
      // Space toggles preview when not in an input
      if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (state.currentFile && !elements.settingsCard.classList.contains('hidden')) {
          e.preventDefault();
          waveformController.togglePlayback();
        }
      }
    });
  }

  // Mobile Navigation
  function setupNavigation() {
    if (elements.navToggle && elements.navMenu) {
      elements.navToggle.addEventListener('click', () => {
        const isOpen = elements.navMenu.classList.toggle('open');
        elements.navToggle.setAttribute('aria-expanded', isOpen);
      });

      // Close mobile menu when clicking a link
      elements.navMenu.querySelectorAll('.nav-link, .nav-cta a').forEach(link => {
        link.addEventListener('click', () => {
          elements.navMenu.classList.remove('open');
          elements.navToggle.setAttribute('aria-expanded', 'false');
        });
      });
    }

    if (elements.errorCloseBtn) {
      elements.errorCloseBtn.addEventListener('click', hideError);
    }
  }

  // Error Presentation
  function showError(title, message) {
    if (elements.globalErrorAlert) {
      elements.errorTitle.textContent = title || 'Error';
      elements.errorMessage.textContent = message || 'An unexpected error occurred.';
      elements.globalErrorAlert.classList.remove('hidden');
      elements.globalErrorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Error';
      elements.sessionStatusPill.style.color = '#EF4444';
    }
  }

  function hideError() {
    if (elements.globalErrorAlert) {
      elements.globalErrorAlert.classList.add('hidden');
    }
    if (elements.sessionStatusPill && state.isProcessing) {
      elements.sessionStatusPill.textContent = 'Processing...';
      elements.sessionStatusPill.style.color = '#00D9FF';
    } else if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = state.audioMetadata ? 'Loaded' : 'Ready';
      elements.sessionStatusPill.style.color = '';
    }
  }

  // Dropzone and File Handling
  function setupDropzone() {
    const dropzone = elements.dropzone;
    const fileInput = elements.fileInput;
    const browseBtn = elements.browseBtn;

    if (!dropzone || !fileInput) return;

    // Click triggers file selector
    dropzone.addEventListener('click', (e) => {
      if (e.target !== browseBtn && !browseBtn.contains(e.target)) {
        fileInput.click();
      }
    });

    browseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput.click();
    });

    // Keyboard support
    dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });

    // Drag and drop events
    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        handleFileSelection(files[0]);
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files.length > 0) {
        handleFileSelection(fileInput.files[0]);
      }
    });
  }

  // Recognized media extensions (case-insensitive)
  const SUPPORTED_MEDIA_EXTENSIONS = [
    'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'oga',
    'opus', 'mp4', 'mpeg', 'mpg', 'm4v', 'webm', 'wma'
  ];

  // Document, archive, and code extensions to reject immediately on the client
  const KNOWN_NON_MEDIA_EXTENSIONS = [
    'txt', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'exe', 'bat', 'cmd', 'sh', 'zip', 'rar', '7z', 'tar',
    'gz', 'iso', 'dmg', 'html', 'htm', 'css', 'js', 'ts',
    'json', 'xml', 'py', 'java', 'c', 'cpp', 'csv'
  ];

  // Pre-validation & Upload Streaming
  function handleFileSelection(file) {
    hideError();

    if (!file || !file.name) {
      showError('No File Selected', 'Please select a valid audio recording to upload.');
      return;
    }

    const fileName = file.name.trim();

    // Extract all extensions case-insensitively
    const nameParts = fileName.split('.');
    const extensions = nameParts.slice(1).map(ext => ext.toLowerCase());
    const finalExt = extensions.length > 0 ? extensions[extensions.length - 1] : '';

    const hasMediaExt = extensions.some(ext => SUPPORTED_MEDIA_EXTENSIONS.includes(ext));

    if (finalExt && KNOWN_NON_MEDIA_EXTENSIONS.includes(finalExt) && !hasMediaExt) {
      showError(
        'Unsupported File Format',
        `The file "${file.name}" is not an audio or video recording. Please select an MP3, WAV, M4A, AAC, FLAC, OGG, or MP4 file.`
      );
      return;
    }

    // Size validation
    if (file.size > state.maxUploadSizeBytes) {
      const maxMb = Math.round(state.maxUploadSizeBytes / (1024 * 1024));
      showError('File Too Large', `The selected file size exceeds the ${maxMb} MB server upload limit.`);
      return;
    }

    if (file.size === 0) {
      showError('Empty File', 'The selected file contains 0 bytes.');
      return;
    }

    state.currentFile = file;

    // Update project badge & session pill
    if (elements.currentProjectBadge) elements.currentProjectBadge.textContent = file.name;
    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Analyzing...';
      elements.sessionStatusPill.style.color = '#00D9FF';
    }

    // Pass to backend for FFprobe inspection
    uploadAndAnalyzeFile(file);
  }

  function uploadAndAnalyzeFile(file) {
    // Show upload progress UI
    elements.dropzone.classList.add('hidden');
    elements.uploadProgressContainer.classList.remove('hidden');
    elements.uploadingFileName.textContent = `Streaming: ${file.name}`;
    elements.uploadProgressFill.style.width = '0%';
    elements.uploadPercentage.textContent = '0%';
    elements.uploadStatusSubtext.textContent = 'Streaming directly to disk buffer...';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/api/audio/analyze`, true);

    // Track upload progress
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 95);
        elements.uploadProgressFill.style.width = `${percent}%`;
        elements.uploadPercentage.textContent = `${percent}%`;
        if (percent >= 95) {
          elements.uploadStatusSubtext.textContent = 'Demuxing audio stream with FFprobe...';
        }
      }
    };

    xhr.onload = () => {
      elements.uploadProgressFill.style.width = '100%';
      elements.uploadPercentage.textContent = '100%';

      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          onAudioAnalyzed(data);
        } catch (err) {
          onUploadError('Failed to parse server analysis response.');
        }
      } else {
        let msg = 'Failed to analyze audio file.';
        try {
          const errRes = JSON.parse(xhr.responseText);
          if (errRes.detail) msg = errRes.detail;
        } catch (_) {}
        onUploadError(msg);
      }
    };

    xhr.onerror = () => {
      onUploadError('Network error connecting to AudioSplit Pro backend.');
    };

    xhr.send(formData);
  }

  function onUploadError(message) {
    elements.uploadProgressContainer.classList.add('hidden');
    elements.dropzone.classList.remove('hidden');
    elements.fileInput.value = '';
    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Error';
      elements.sessionStatusPill.style.color = '#EF4444';
    }
    showError('Audio Analysis Failed', message);
  }

  function onAudioAnalyzed(data) {
    state.jobId = data.job_id;
    state.audioMetadata = data;

    // Reset upload UI and transition to workstation settings
    elements.uploadProgressContainer.classList.add('hidden');
    elements.uploadCard.classList.add('hidden');
    elements.settingsCard.classList.remove('hidden');

    // Populate metadata
    elements.metaFilename.textContent = data.filename;
    elements.metaDuration.textContent = `${data.formatted_duration} (${data.human_duration})`;
    elements.metaSize.textContent = data.formatted_size;
    elements.metaCodec.textContent = `${data.codec.toUpperCase()} (${data.detected_format})`;
    elements.metaSampleRate.textContent = data.sample_rate;
    elements.metaChannelsBitrate.textContent = `${data.channel_layout || data.channels + ' ch'} • ${data.bit_rate}`;

    if (elements.currentProjectBadge) elements.currentProjectBadge.textContent = data.filename;
    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Loaded';
      elements.sessionStatusPill.style.color = '#10B981';
    }

    if (data.is_video_container) {
      elements.videoNotice.classList.remove('hidden');
    } else {
      elements.videoNotice.classList.add('hidden');
    }

    // Default duration is 30 mins
    setDurationPreset(30.0);
    updateEstimator();

    // Initialize waveform rendering
    if (state.currentFile) {
      waveformController.loadFile(state.currentFile, data);
    }

    // Add log entry
    addHistoryLog(`[ANALYSIS] ${data.filename} (${data.formatted_duration}) &bull; ${data.codec} &bull; ${data.sample_rate}`);
  }

  // Duration Presets & Custom Input
  function setupSplitControls() {
    elements.presetButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        elements.presetButtons.forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');

        const minutesVal = btn.getAttribute('data-minutes');
        if (minutesVal === 'custom') {
          state.isCustomDuration = true;
          elements.customDurationBox.classList.remove('hidden');
          const customVal = parseFloat(elements.customMinutesInput.value);
          state.splitDurationMinutes = isNaN(customVal) || customVal <= 0 ? 30.0 : customVal;
        } else {
          state.isCustomDuration = false;
          elements.customDurationBox.classList.add('hidden');
          state.splitDurationMinutes = parseFloat(minutesVal);
        }
        updateEstimator();
      });
    });

    if (elements.customMinutesInput) {
      elements.customMinutesInput.addEventListener('input', () => {
        const val = parseFloat(elements.customMinutesInput.value);
        if (!isNaN(val) && val > 0) {
          state.splitDurationMinutes = val;
          updateEstimator();
        }
      });
    }
  }

  function setDurationPreset(minutes) {
    elements.presetButtons.forEach(b => {
      const bMin = b.getAttribute('data-minutes');
      if (parseFloat(bMin) === minutes) {
        b.classList.add('active');
        b.setAttribute('aria-checked', 'true');
      } else {
        b.classList.remove('active');
        b.setAttribute('aria-checked', 'false');
      }
    });
    elements.customDurationBox.classList.add('hidden');
    state.isCustomDuration = false;
    state.splitDurationMinutes = minutes;
  }

  // Dynamic Segment Estimator & Waveform Split Markers Update
  function updateEstimator() {
    if (!state.audioMetadata || !state.splitDurationMinutes || state.splitDurationMinutes <= 0) {
      elements.estSegmentsCount.textContent = '-';
      elements.estSegmentsDetails.textContent = 'Upload an audio file to view estimated segments.';
      waveformController.updateSplitMarkers(0, 0);
      return;
    }

    const totalSeconds = state.audioMetadata.duration_seconds;
    const splitSeconds = state.splitDurationMinutes * 60.0;
    const count = Math.max(1, Math.ceil(totalSeconds / splitSeconds));

    elements.estSegmentsCount.textContent = count === 1 ? '1 Segment' : `${count} Segments`;

    if (count === 1) {
      elements.estSegmentsDetails.textContent = `Interval (${state.splitDurationMinutes}m) exceeds total length (${state.audioMetadata.formatted_duration}). 1 complete file will be generated.`;
    } else {
      const remainingSeconds = totalSeconds - ((count - 1) * splitSeconds);
      const remainingMinutes = (remainingSeconds / 60).toFixed(1);
      elements.estSegmentsDetails.textContent = `${count - 1} segment(s) of ~${state.splitDurationMinutes}m, and final segment of ~${remainingMinutes}m (preserving all trailing audio).`;
    }

    // Update cuts overlay on waveform canvas
    waveformController.updateSplitMarkers(totalSeconds, state.splitDurationMinutes);
  }

  // Splitting Action & Polling
  function setupActions() {
    elements.startSplitBtn.addEventListener('click', startAudioSplitting);
    elements.resetFileBtn.addEventListener('click', resetAll);
    elements.splitAnotherBtn.addEventListener('click', resetAll);
  }

  async function startAudioSplitting() {
    if (state.isProcessing || !state.jobId) return;

    if (state.isCustomDuration) {
      const val = parseFloat(elements.customMinutesInput.value);
      if (isNaN(val) || val <= 0) {
        showError('Invalid Split Duration', 'Please enter a valid positive number of minutes for the custom split duration.');
        return;
      }
      state.splitDurationMinutes = val;
    }

    state.isProcessing = true;
    hideError();

    // Transition to processing UI
    elements.settingsCard.classList.add('hidden');
    elements.processingCard.classList.remove('hidden');
    elements.processingStatusTitle.textContent = 'Splitting Audio Recording';
    elements.processingStatusMessage.textContent = 'Starting background processing...';
    elements.jobProgressFill.style.width = '5%';
    elements.jobProgressPercent.textContent = '5%';
    elements.jobSegmentCounter.textContent = 'Preparing segments...';

    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Processing...';
      elements.sessionStatusPill.style.color = '#00D9FF';
    }

    addHistoryLog(`[SPLIT START] Job ${state.jobId} &bull; Interval: ${state.splitDurationMinutes}m`);

    try {
      const response = await fetch(`${API_BASE}/api/audio/split`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: state.jobId,
          split_duration_minutes: state.splitDurationMinutes
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start audio splitting.');
      }

      startStatusPolling();
    } catch (err) {
      state.isProcessing = false;
      elements.processingCard.classList.add('hidden');
      elements.settingsCard.classList.remove('hidden');
      showError('Splitting Request Failed', err.message);
    }
  }

  function startStatusPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);

    state.pollTimer = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/audio/jobs/${state.jobId}`);
        if (!response.ok) {
          throw new Error('Lost connection to audio splitting job.');
        }

        const data = await response.json();
        handleJobStatusUpdate(data);
      } catch (err) {
        clearInterval(state.pollTimer);
        state.isProcessing = false;
        elements.processingCard.classList.add('hidden');
        elements.settingsCard.classList.remove('hidden');
        showError('Processing Error', err.message);
      }
    }, 400);
  }

  async function handleJobStatusUpdate(job) {
    const progress = Math.max(5, Math.min(100, Math.round(job.progress_percent || 0)));
    elements.jobProgressFill.style.width = `${progress}%`;
    elements.jobProgressPercent.textContent = `${progress}%`;

    elements.processingStatusTitle.textContent = job.status === 'processing' 
      ? 'Splitting Audio Recording' 
      : (job.status === 'queued' ? 'Initializing Audio Splitting' : 'Processing Audio');

    if (elements.processingStatusMessage && job.message) {
      elements.processingStatusMessage.textContent = job.message;
    }

    if (elements.jobSegmentCounter && job.total_segments && job.total_segments > 0) {
      const completed = job.completed_segments || 0;
      elements.jobSegmentCounter.textContent = completed > 0 
        ? `Segment ${completed} of ${job.total_segments}`
        : `Processing 1 of ${job.total_segments}`;
    }

    if (job.status === 'completed') {
      clearInterval(state.pollTimer);
      state.isProcessing = false;
      await fetchAndDisplayResults();
    } else if (job.status === 'failed') {
      clearInterval(state.pollTimer);
      state.isProcessing = false;
      elements.processingCard.classList.add('hidden');
      elements.settingsCard.classList.remove('hidden');
      if (elements.sessionStatusPill) {
        elements.sessionStatusPill.textContent = 'Failed';
        elements.sessionStatusPill.style.color = '#EF4444';
      }
      showError('Audio Processing Failed', job.error || 'FFmpeg encountered an error while splitting the audio.');
    }
  }

  async function fetchAndDisplayResults() {
    try {
      const response = await fetch(`${API_BASE}/api/audio/jobs/${state.jobId}/results`);
      if (!response.ok) {
        throw new Error('Unable to fetch generated audio segment metadata.');
      }

      const results = await response.json();
      renderResults(results);
    } catch (err) {
      elements.processingCard.classList.add('hidden');
      elements.settingsCard.classList.remove('hidden');
      showError('Failed to Retrieve Results', err.message);
    }
  }

  function renderResults(results) {
    elements.processingCard.classList.add('hidden');
    elements.resultsCard.classList.remove('hidden');

    elements.resultsSubtitle.textContent = `Generated ${results.total_segments} audio segments (${results.split_duration_minutes} min intervals).`;
    elements.zipSizeDisplay.textContent = `Includes all ${results.total_segments} audio parts • ${results.formatted_zip_size}`;
    elements.downloadZipBtn.href = `${API_BASE}${results.zip_download_url}`;

    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Complete';
      elements.sessionStatusPill.style.color = '#10B981';
    }

    // Render individual segments
    elements.segmentsList.innerHTML = '';
    results.segments.forEach(seg => {
      const row = document.createElement('div');
      row.className = 'segment-item';
      row.innerHTML = `
        <div class="segment-left">
          <span class="segment-num-badge font-mono">Part ${String(seg.segment_number).padStart(2, '0')}</span>
          <div class="segment-details">
            <span class="segment-name font-mono">${escapeHtml(seg.filename)}</span>
            <div class="segment-meta font-mono">
              <span>Duration: ${seg.formatted_duration}</span>
              <span class="meta-dot"></span>
              <span>Size: ${seg.formatted_size}</span>
            </div>
          </div>
        </div>
        <a href="${API_BASE}${seg.download_url}" class="btn btn-outline btn-sm btn-icon-text font-mono" download>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          Download
        </a>
      `;
      elements.segmentsList.appendChild(row);
    });

    // Record session into Recent Projects & History Log
    addRecentProjectSession(state.audioMetadata, results);
    addHistoryLog(`[COMPLETE] Sliced into ${results.total_segments} segments &bull; Archive size: ${results.formatted_zip_size}`);
  }

  // Session Logging & Projects Table Helpers
  function addRecentProjectSession(meta, results) {
    if (!elements.projectsTableBody || !meta || !results) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="text-white">${escapeHtml(meta.filename)}</td>
      <td>${meta.formatted_duration}</td>
      <td>${results.split_duration_minutes} min</td>
      <td>${results.total_segments} Parts</td>
      <td>${meta.codec.toUpperCase()}</td>
      <td><span class="table-badge-ok">COMPLETE</span></td>
    `;
    elements.projectsTableBody.prepend(tr);
  }

  function addHistoryLog(message) {
    if (!elements.historyLogBox) return;
    const time = new Date().toLocaleTimeString();
    const div = document.createElement('div');
    div.className = 'log-line';
    div.innerHTML = `<span class="log-time">[${time}]</span> ${message}`;
    elements.historyLogBox.appendChild(div);
    elements.historyLogBox.scrollTop = elements.historyLogBox.scrollHeight;
  }

  // Cleanup & Reset
  async function resetAll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }

    if (state.jobId && !state.isProcessing) {
      try {
        fetch(`${API_BASE}/api/audio/jobs/${state.jobId}`, { method: 'DELETE' });
      } catch (_) {}
    }

    waveformController.reset();

    state.jobId = null;
    state.audioMetadata = null;
    state.currentFile = null;
    state.isProcessing = false;

    // Reset UI cards
    elements.resultsCard.classList.add('hidden');
    elements.processingCard.classList.add('hidden');
    elements.settingsCard.classList.add('hidden');
    elements.uploadCard.classList.remove('hidden');
    elements.dropzone.classList.remove('hidden');
    elements.uploadProgressContainer.classList.add('hidden');
    elements.fileInput.value = '';

    if (elements.currentProjectBadge) elements.currentProjectBadge.textContent = 'Untitled Session';
    if (elements.sessionStatusPill) {
      elements.sessionStatusPill.textContent = 'Ready';
      elements.sessionStatusPill.style.color = '';
    }

    hideError();
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
