(function () {
  const form = document.getElementById("ask-form");
  const input = document.getElementById("ask-question");
  const loading = document.getElementById("ask-loading");
  const feed = document.getElementById("ask-feed");

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;

    loading.hidden = false;
    form.querySelector("button").disabled = true;

    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        loading.hidden = true;
        form.querySelector("button").disabled = false;

        if (!ok) {
          alert(data.error || "Something went wrong — try again.");
          return;
        }

        const emptyState = feed.querySelector(".empty-state");
        if (emptyState) emptyState.remove();

        const div = document.createElement("div");
        div.className = "regs-qa";
        let cites = "";
        if (data.citations && data.citations.length) {
          const bySource = {};
          data.citations.forEach((c) => {
            (bySource[c.source] = bySource[c.source] || []).push(c.page);
          });
          const formatted = Object.entries(bySource)
            .map(([source, pages]) => `${escapeHtml(source)} p.${pages.join(", ")}`)
            .join(" · ");
          cites = `<div class="regs-cites">Source: ${formatted}</div>`;
        }
        div.innerHTML = `
          <div class="regs-question"><strong>${escapeHtml(data.user_name)}</strong> asked: ${escapeHtml(data.question)}</div>
          <div class="regs-answer">${escapeHtml(data.answer)}</div>
          ${cites}
          <div class="comment-meta">just now</div>
        `;
        feed.prepend(div);
        input.value = "";
      })
      .catch(() => {
        loading.hidden = true;
        form.querySelector("button").disabled = false;
        alert("Something went wrong — try again.");
      });
  });
})();
