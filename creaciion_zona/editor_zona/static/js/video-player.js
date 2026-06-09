import { formatTime } from "./utils.js";

export class VideoPlayerController {
  constructor({
    video,
    playPauseButton,
    backwardButton,
    forwardButton,
    speedSelect,
    timeReadout,
    onMetadataLoaded,
  }) {
    this.video = video;
    this.playPauseButton = playPauseButton;
    this.backwardButton = backwardButton;
    this.forwardButton = forwardButton;
    this.speedSelect = speedSelect;
    this.timeReadout = timeReadout;
    this.onMetadataLoaded = onMetadataLoaded;
  }

  initialize() {
    this.bindEvents();
    this.updatePlaybackButton();
    this.updateTimeReadout();
    this.speedSelect.value = String(this.video.playbackRate || 1);
  }

  bindEvents() {
    this.playPauseButton.addEventListener("click", () => {
      void this.togglePlayback();
    });

    this.backwardButton.addEventListener("click", () => {
      this.seek(-5);
    });

    this.forwardButton.addEventListener("click", () => {
      this.seek(5);
    });

    this.speedSelect.addEventListener("change", () => {
      this.video.playbackRate = Number(this.speedSelect.value);
    });

    this.video.addEventListener("loadedmetadata", () => {
      this.onMetadataLoaded?.();
      this.updateTimeReadout();
    });

    this.video.addEventListener("timeupdate", () => {
      this.updateTimeReadout();
    });

    this.video.addEventListener("play", () => {
      this.updatePlaybackButton();
    });

    this.video.addEventListener("pause", () => {
      this.updatePlaybackButton();
    });
  }

  async togglePlayback() {
    if (this.video.paused) {
      await this.video.play();
      return;
    }

    this.video.pause();
  }

  seek(deltaSeconds) {
    const duration = Number.isFinite(this.video.duration)
      ? this.video.duration
      : this.video.currentTime + Math.abs(deltaSeconds);
    const nextTime = this.video.currentTime + deltaSeconds;
    this.video.currentTime = Math.min(duration, Math.max(0, nextTime));
  }

  updatePlaybackButton() {
    this.playPauseButton.textContent = this.video.paused ? "Reproducir" : "Pausar";
  }

  updateTimeReadout() {
    this.timeReadout.textContent = `Tiempo: ${formatTime(this.video.currentTime)} / ${formatTime(this.video.duration)}`;
  }
}
