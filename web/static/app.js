document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("generator-form");
  const generateBtn = document.getElementById("generate-btn");
  const progressContainer = document.getElementById("progress-container");
  const progressMsg = document.getElementById("progress-msg");
  const errorBanner = document.getElementById("error-banner");
  const loadDemoBtn = document.getElementById("load-demo-btn");
  const textInput = document.getElementById("text-input");
  const dateInput = document.getElementById("date-input");

  const imageFileInput = document.getElementById("image-file");
  const gifFileInput = document.getElementById("gif-file");
  const gif2FileInput = document.getElementById("gif2-file");
  const musicFileInput = document.getElementById("music-file");

  const imagePreview = document.getElementById("image-preview");
  const gifPreview = document.getElementById("gif-preview");
  const gif2Preview = document.getElementById("gif2-preview");
  const musicPreview = document.getElementById("music-preview");

  const placeholderScreen = document.getElementById("placeholder-screen");
  const videoPlayer = document.getElementById("video-player");
  const actionBar = document.getElementById("action-bar");
  const downloadBtn = document.getElementById("download-btn");

  let useDemoAssets = false;
  let timerInterval = null;
  const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

  function showError(message) {
    if (errorBanner) {
      errorBanner.textContent = message;
      errorBanner.classList.remove("hidden");
    }
  }

  function clearError() {
    if (errorBanner) {
      errorBanner.textContent = "";
      errorBanner.classList.add("hidden");
    }
  }

  function validateFileSize(file, label) {
    if (file && file.size > MAX_FILE_SIZE_BYTES) {
      showError(`⚠️ File "${file.name}" for ${label} exceeds 25 MB limit.`);
      return false;
    }
    return true;
  }

  // File change labels
  imageFileInput.addEventListener("change", (e) => {
    useDemoAssets = false;
    clearError();
    const file = e.target.files[0];
    if (file && validateFileSize(file, "Picture")) {
      imagePreview.textContent = `✓ ${file.name}`;
    } else {
      imagePreview.textContent = "No picture chosen";
    }
  });

  gifFileInput.addEventListener("change", (e) => {
    useDemoAssets = false;
    clearError();
    const file = e.target.files[0];
    if (file && validateFileSize(file, "GIF 1")) {
      gifPreview.textContent = `✓ ${file.name}`;
    } else {
      gifPreview.textContent = "No GIF chosen";
    }
  });

  gif2FileInput.addEventListener("change", (e) => {
    useDemoAssets = false;
    clearError();
    const file = e.target.files[0];
    if (file && validateFileSize(file, "GIF 2")) {
      gif2Preview.textContent = `✓ ${file.name}`;
    } else {
      gif2Preview.textContent = "Optional 2nd GIF";
    }
  });

  musicFileInput.addEventListener("change", (e) => {
    useDemoAssets = false;
    clearError();
    const file = e.target.files[0];
    if (file && validateFileSize(file, "Music")) {
      musicPreview.textContent = `✓ ${file.name}`;
    } else {
      musicPreview.textContent = "No music chosen";
    }
  });

  // Setup drag and drop for each upload card
  function setupDropzone(cardId, fileInput, previewEl, label) {
    const card = document.getElementById(cardId);
    if (!card) return;

    ["dragenter", "dragover"].forEach((eventName) => {
      card.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        card.classList.add("dragover");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      card.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        card.classList.remove("dragover");
      });
    });

    card.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        if (validateFileSize(files[0], label)) {
          fileInput.files = files;
          useDemoAssets = false;
          clearError();
          previewEl.textContent = `✓ ${files[0].name}`;
        }
      }
    });
  }

  setupDropzone("image-card", imageFileInput, imagePreview, "Picture");
  setupDropzone("gif-card", gifFileInput, gifPreview, "GIF 1");
  setupDropzone("gif2-card", gif2FileInput, gif2Preview, "GIF 2");
  setupDropzone("music-card", musicFileInput, musicPreview, "Music");

  // Load Demo Assets button
  loadDemoBtn.addEventListener("click", () => {
    useDemoAssets = true;
    clearError();
    textInput.value = "Every sunrise brings a new beginning ✨\nEmbrace the journey today 🚀❤️";
    dateInput.value = "";
    imagePreview.textContent = "✨ unnamed.jpg";
    gifPreview.textContent = "✨ giphy.gif (Slot 1)";
    gif2Preview.textContent = "✨ giphy1.gif (Slot 2)";
    musicPreview.textContent = "✨ bg.mpeg (Music)";
  });

  // Default text
  if (!textInput.value) {
    textInput.value = "Every sunrise brings a new beginning ✨\nEmbrace the journey today 🚀❤️";
  }

  // Handle Video Generation Submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    const rawText = textInput.value.trim();
    if (!rawText) {
      showError("Please enter a quote or message for the video.");
      return;
    }

    generateBtn.disabled = true;
    progressContainer.classList.remove("hidden");
    actionBar.classList.add("hidden");

    let secondsElapsed = 0;
    progressMsg.textContent = "Compositing elements & rendering with FFmpeg (0s)...";
    timerInterval = setInterval(() => {
      secondsElapsed++;
      progressMsg.textContent = `Compositing elements & rendering with FFmpeg (${secondsElapsed}s)...`;
    }, 1000);

    const formData = new FormData(form);
    if (useDemoAssets) {
      formData.append("use_demo", "true");
    }

    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${response.status})`);
      }

      const result = await response.json();
      const videoUrl = result.video_url + "?t=" + new Date().getTime();

      // Show video in phone screen
      placeholderScreen.classList.add("hidden");
      videoPlayer.src = videoUrl;
      videoPlayer.classList.remove("hidden");
      videoPlayer.volume = 1.0;
      videoPlayer.muted = false;

      videoPlayer.play().catch(err => {
        console.warn("Browser blocked unmuted autoplay:", err);
        videoPlayer.muted = true;
        videoPlayer.play();
      });

      // Setup download button
      downloadBtn.href = videoUrl;
      downloadBtn.download = result.filename || "my_portrait_video.mp4";
      actionBar.classList.remove("hidden");

    } catch (err) {
      showError("❌ Error generating video: " + err.message);
    } finally {
      clearInterval(timerInterval);
      generateBtn.disabled = false;
      progressContainer.classList.add("hidden");
    }
  });
});
