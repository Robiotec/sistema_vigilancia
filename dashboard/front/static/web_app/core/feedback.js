import { byId } from "./dom.js";

export function setFeedback(id, message, tone = "info") {
  const feedback = byId(id);
  if (!feedback) return;

  feedback.hidden = false;
  feedback.textContent = message;
  if (tone === "success" || tone === "error" || tone === "info") {
    feedback.dataset.tone = tone;
    return;
  }
  delete feedback.dataset.tone;
}
