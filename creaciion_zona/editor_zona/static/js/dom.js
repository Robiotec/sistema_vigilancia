function getRequiredElement(id) {
  const element = document.getElementById(id);

  if (!element) {
    throw new Error(`No se encontro el elemento #${id}.`);
  }

  return element;
}

export const elements = {
  video: getRequiredElement("video"),
  overlay: getRequiredElement("overlay"),
  stage: getRequiredElement("stage"),
  playPauseButton: getRequiredElement("play-pause"),
  closePolygonButton: getRequiredElement("close-polygon"),
  undoPointButton: getRequiredElement("undo-point"),
  clearPolygonButton: getRequiredElement("clear-polygon"),
  copyJsonButton: getRequiredElement("copy-json"),
  backwardButton: getRequiredElement("backward"),
  forwardButton: getRequiredElement("forward"),
  speedSelect: getRequiredElement("speed"),
  output: getRequiredElement("output"),
  timeReadout: getRequiredElement("time-readout"),
  pointCount: getRequiredElement("point-count"),
  videoSize: getRequiredElement("video-size"),
  stateBadge: getRequiredElement("state-badge"),
  copyFeedback: getRequiredElement("copy-feedback"),
};

export const pageData = {
  videoName: document.body.dataset.videoName || "video.mp4",
};
