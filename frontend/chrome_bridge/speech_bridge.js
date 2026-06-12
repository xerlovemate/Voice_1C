(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const statusEl = document.getElementById("status");
  const interimEl = document.getElementById("interim");
  const finalEl = document.getElementById("final");
  const meterEl = document.getElementById("meter");
  let recognition = null;
  let listening = false;
  let keepAlive = true;

  function setStatus(status, extra = {}) {
    statusEl.textContent = status;
    post("/api/state", { status, ...extra });
  }

  async function post(url, payload) {
    try {
      await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (error) {
      console.warn("Voice1C bridge post failed", error);
    }
  }

  function estimateLevel(text) {
    const level = Math.min(1, Math.max(0.06, String(text || "").length / 42));
    meterEl.style.width = Math.round(level * 100) + "%";
    post("/api/speech/level", { level });
  }

  function createRecognition() {
    if (!SpeechRecognition) {
      setStatus("error", { error: "Web Speech API is not available" });
      return null;
    }
    const instance = new SpeechRecognition();
    instance.lang = "ru-RU";
    instance.continuous = true;
    instance.interimResults = true;
    instance.maxAlternatives = 1;

    instance.onstart = () => {
      listening = true;
      setStatus("listening", { api_available: true });
    };
    instance.onaudiostart = () => setStatus("audio-start");
    instance.onspeechstart = () => setStatus("speech-start");
    instance.onspeechend = () => setStatus("speech-end");
    instance.onaudioend = () => {
      meterEl.style.width = "0%";
      post("/api/speech/level", { level: 0 });
    };
    instance.onerror = (event) => {
      const error = event.error || "unknown";
      setStatus("error", { error });
      post("/api/speech/error", { error });
    };
    instance.onend = () => {
      listening = false;
      setStatus("stopped");
      if (keepAlive) {
        setTimeout(() => {
          if (keepAlive && !listening) start();
        }, 350);
      }
    };
    instance.onresult = (event) => {
      let interim = "";
      const finals = [];
      let confidence = null;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const alternative = result[0];
        const transcript = (alternative?.transcript || "").trim();
        if (!transcript) continue;
        if (result.isFinal) {
          finals.push(transcript);
          confidence = alternative.confidence;
        } else {
          interim += transcript + " ";
        }
      }
      interim = interim.trim();
      if (interim) {
        interimEl.textContent = interim;
        estimateLevel(interim);
        post("/api/speech/interim", { text: interim, confidence });
      }
      for (const text of finals) {
        finalEl.textContent = text;
        interimEl.textContent = "";
        estimateLevel(text);
        post("/api/speech/final", { text, confidence });
      }
    };
    return instance;
  }

  function start() {
    if (listening) return true;
    keepAlive = true;
    recognition = recognition || createRecognition();
    if (!recognition) return false;
    try {
      recognition.start();
      return true;
    } catch (error) {
      if (!String(error).includes("already started")) {
        post("/api/speech/error", { error: String(error) });
        setStatus("error", { error: String(error) });
      }
      return false;
    }
  }

  function stop() {
    keepAlive = false;
    try {
      recognition?.stop();
    } catch (error) {
      console.warn(error);
    }
    meterEl.style.width = "0%";
    post("/api/speech/level", { level: 0 });
    setStatus("stopped");
  }

  window.voice1cBridge = {
    start,
    stop,
    capabilities() {
      return {
        speechApiAvailable: Boolean(SpeechRecognition),
        protocol: location.protocol,
        userAgent: navigator.userAgent,
      };
    },
  };
  window.voice1cStart = start;
  window.voice1cStop = stop;

  document.getElementById("start").addEventListener("click", start);
  document.getElementById("stop").addEventListener("click", stop);

  setStatus(SpeechRecognition ? "ready" : "error", {
    api_available: Boolean(SpeechRecognition),
    error: SpeechRecognition ? "" : "Web Speech API is not available",
  });
})();
