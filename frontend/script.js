/**
 * AudioSplit Pro - Client Application Logic
 * Modern Vanilla JavaScript with Fetch API & XMLHttpRequest Progress
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
    splitDurationMinutes: 30.0,
    isCustomDuration: false,
    pollTimer: null,
    isProcessing: false,
    maxUploadSizeBytes: 500 * 1024 * 1024 // 500 MB
  };

  // DOM Elements
  const elements = {
    // Nav
    navToggle: document.getElementById('navToggle'),
    navMenu: document.getElementById('navMenu'),

    // Alerts
    globalErrorAlert: document.getElementById('globalErrorAlert'),
    errorTitle: document.getElementById('errorTitle'),
    errorMessage: document.getElementById('errorMessage'),
    errorCloseBtn: document.getElementById('errorCloseBtn'),

    // Cards
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
    splitAnotherBtn: document.getElementById('splitAnotherBtn')
  };

  // Initialize
  function init() {
    setupNavigation();
    setupDropzone();
    setupSplitControls();
    setupActions();
    updateEstimator();

    const currentYearEl = document.getElementById('currentYear');
    if (currentYearEl) {
      currentYearEl.textContent = new Date().getFullYear();
    }
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
  }

  function hideError() {
    if (elements.globalErrorAlert) {
      elements.globalErrorAlert.classList.add('hidden');
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

    // Extract all extensions case-insensitively, e.g. "Audio_Part_1.MP3.mpeg" -> ["mp3", "mpeg"]
    const nameParts = fileName.split('.');
    const extensions = nameParts.slice(1).map(ext => ext.toLowerCase());
    const finalExt = extensions.length > 0 ? extensions[extensions.length - 1] : '';

    const hasMediaExt = extensions.some(ext => SUPPORTED_MEDIA_EXTENSIONS.includes(ext));
    const hasMediaMime = file.type && (
      file.type.startsWith('audio/') ||
      file.type.startsWith('video/') ||
      file.type === 'video/mp4'
    );

    // Reject obvious non-media files if no media extension exists in the filename
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

    // Pass to backend for FFprobe inspection and audio stream validation
    uploadAndAnalyzeFile(file);
  }

  function uploadAndAnalyzeFile(file) {
    // Show upload progress UI
    elements.dropzone.classList.add('hidden');
    elements.uploadProgressContainer.classList.remove('hidden');
    elements.uploadingFileName.textContent = `Uploading: ${file.name}`;
    elements.uploadProgressFill.style.width = '0%';
    elements.uploadPercentage.textContent = '0%';
    elements.uploadStatusSubtext.textContent = 'Streaming directly to server storage...';

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
          elements.uploadStatusSubtext.textContent = 'Analyzing audio streams with FFprobe...';
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
    showError('Audio Analysis Failed', message);
  }

  function onAudioAnalyzed(data) {
    state.jobId = data.job_id;
    state.audioMetadata = data;

    // Reset upload UI
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

    if (data.is_video_container) {
      elements.videoNotice.classList.remove('hidden');
    } else {
      elements.videoNotice.classList.add('hidden');
    }

    // Default duration is 30 mins
    setDurationPreset(30.0);
    updateEstimator();

    // Smooth scroll to settings
    elements.settingsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

  // Dynamic Segment Estimator
  function updateEstimator() {
    if (!state.audioMetadata || !state.splitDurationMinutes || state.splitDurationMinutes <= 0) {
      elements.estSegmentsCount.textContent = '-';
      elements.estSegmentsDetails.textContent = 'Upload an audio file to view estimated segments.';
      return;
    }

    const totalSeconds = state.audioMetadata.duration_seconds;
    const splitSeconds = state.splitDurationMinutes * 60.0;
    const count = Math.max(1, Math.ceil(totalSeconds / splitSeconds));

    elements.estSegmentsCount.textContent = count === 1 ? '1 Segment' : `${count} Segments`;

    if (count === 1) {
      elements.estSegmentsDetails.textContent = `The selected duration (${state.splitDurationMinutes} min) is longer than the audio (${state.audioMetadata.formatted_duration}). 1 complete file will be generated.`;
    } else {
      const remainingSeconds = totalSeconds - ((count - 1) * splitSeconds);
      const remainingMinutes = (remainingSeconds / 60).toFixed(1);
      elements.estSegmentsDetails.textContent = `${count - 1} segment(s) of ~${state.splitDurationMinutes} min, and final segment of ~${remainingMinutes} min (preserving all trailing audio).`;
    }
  }

  // Splitting Action & Polling
  function setupActions() {
    // Start Split Button
    elements.startSplitBtn.addEventListener('click', startAudioSplitting);

    // Replace File / Reset
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
    elements.processingCard.scrollIntoView({ behavior: 'smooth', block: 'start' });

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

      // Begin polling job status
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

    elements.resultsSubtitle.textContent = `Successfully split into ${results.total_segments} audio segments (${results.split_duration_minutes} min intervals).`;
    elements.zipSizeDisplay.textContent = `Includes all ${results.total_segments} audio parts • ${results.formatted_zip_size}`;
    elements.downloadZipBtn.href = `${API_BASE}${results.zip_download_url}`;

    // Render individual segments
    elements.segmentsList.innerHTML = '';
    results.segments.forEach(seg => {
      const row = document.createElement('div');
      row.className = 'segment-item';
      row.innerHTML = `
        <div class="segment-left">
          <span class="segment-num-badge">Part ${String(seg.segment_number).padStart(2, '0')}</span>
          <div class="segment-details">
            <span class="segment-name font-mono">${escapeHtml(seg.filename)}</span>
            <div class="segment-meta font-mono">
              <span>Duration: ${seg.formatted_duration}</span>
              <span class="meta-dot"></span>
              <span>Size: ${seg.formatted_size}</span>
            </div>
          </div>
        </div>
        <a href="${API_BASE}${seg.download_url}" class="btn btn-outline btn-sm btn-icon-text" download>
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

    elements.resultsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Cleanup & Reset
  async function resetAll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }

    // Call DELETE API in background to clean up server files
    if (state.jobId && !state.isProcessing) {
      try {
        fetch(`${API_BASE}/api/audio/jobs/${state.jobId}`, { method: 'DELETE' });
      } catch (_) {}
    }

    state.jobId = null;
    state.audioMetadata = null;
    state.isProcessing = false;

    // Reset UI cards
    elements.resultsCard.classList.add('hidden');
    elements.processingCard.classList.add('hidden');
    elements.settingsCard.classList.add('hidden');
    elements.uploadCard.classList.remove('hidden');
    elements.dropzone.classList.remove('hidden');
    elements.uploadProgressContainer.classList.add('hidden');
    elements.fileInput.value = '';
    hideError();

    elements.uploadCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
