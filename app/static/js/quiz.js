(function () {
  const form = document.getElementById("quiz-form");
  const resultEl = document.getElementById("quiz-result");
  if (!form) return;

  const videoId = form.dataset.videoId;

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const answers = {};
    form.querySelectorAll(".quiz-question").forEach((fieldset) => {
      const qid = fieldset.dataset.questionId;
      const checked = fieldset.querySelector("input[type=radio]:checked");
      if (checked) answers[qid] = parseInt(checked.value, 10);
    });

    fetch(`/video/${videoId}/quiz/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    })
      .then((r) => r.json())
      .then((data) => {
        resultEl.hidden = false;
        resultEl.classList.toggle("correct", data.score === data.total);
        resultEl.textContent = `You scored ${data.score} out of ${data.total}.`;
        form.querySelectorAll("input[type=radio]").forEach((i) => (i.disabled = true));
        form.querySelector("button[type=submit]").disabled = true;
        resultEl.scrollIntoView({ behavior: "smooth" });
      });
  });
})();
