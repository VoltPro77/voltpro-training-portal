(function () {
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function reloadIfJustCompleted(data) {
    if (data.completed) {
      const cta = document.querySelector(".quiz-cta");
      if (cta && !cta.querySelector(".btn-pill")) {
        location.reload();
      }
    }
  }

  // ---------- Hosted video player (progress tracked via timeupdate) ----------
  const player = document.getElementById("player");
  if (player) {
    const statusEl = document.getElementById("progress-status");
    const videoId = player.dataset.videoId;
    const resumeSeconds = parseFloat(player.dataset.resumeSeconds || "0");

    player.addEventListener("loadedmetadata", () => {
      if (resumeSeconds > 0 && resumeSeconds < player.duration - 5) {
        player.currentTime = resumeSeconds;
      }
    });

    let lastSent = 0;

    function sendProgress() {
      if (!player.duration) return;
      const seconds = Math.floor(player.currentTime);
      if (seconds === lastSent) return;
      lastSent = seconds;

      fetch("/api/progress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: videoId, seconds_watched: seconds, duration: player.duration }),
      })
        .then((r) => r.json())
        .then((data) => {
          const pct = Math.round((data.percent_complete || 0) * 100);
          statusEl.textContent = data.completed ? "Completed — quiz unlocked." : `${pct}% watched`;
          reloadIfJustCompleted(data);
        })
        .catch(() => {});
    }

    player.addEventListener("timeupdate", () => {
      if (Math.floor(player.currentTime) % 5 === 0) sendProgress();
    });
    player.addEventListener("pause", sendProgress);
    player.addEventListener("ended", sendProgress);
    window.addEventListener("beforeunload", sendProgress);
  }

  // ---------- Linked YouTube video (manual "mark as watched", no auto-tracking) ----------
  const markWatchedBtn = document.getElementById("mark-watched-btn");
  if (markWatchedBtn) {
    markWatchedBtn.addEventListener("click", () => {
      markWatchedBtn.disabled = true;
      const videoId = markWatchedBtn.dataset.videoId;

      fetch("/api/progress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: videoId, seconds_watched: 1, duration: 1 }),
      })
        .then((r) => r.json())
        .then((data) => {
          reloadIfJustCompleted(data);
        })
        .catch(() => {
          markWatchedBtn.disabled = false;
        });
    });
  }

  // ---------- Comments (always active, regardless of video type) ----------
  const form = document.getElementById("comment-form");
  if (form) {
    const body = document.getElementById("comment-body");
    const list = document.getElementById("comment-list");
    const videoId = (document.getElementById("player") || document.getElementById("mark-watched-btn") || {}).dataset
      ?.videoId;

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = body.value.trim();
      if (!text) return;

      fetch(`/api/videos/${videoId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: text }),
      })
        .then((r) => r.json())
        .then((comment) => {
          const emptyState = list.querySelector(".empty-state");
          if (emptyState) emptyState.remove();

          const div = document.createElement("div");
          div.className = "comment";
          div.id = `comment-${comment.id}`;
          div.innerHTML = `
            <div class="comment-meta"><strong>${escapeHtml(comment.user_name)}</strong></div>
            <div class="comment-body">${escapeHtml(comment.body)}</div>
          `;
          list.prepend(div);
          body.value = "";
        });
    });
  }
})();
