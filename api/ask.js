// Vercel 서버 함수: 사이트의 AI 버튼과 챗봇이 이 주소(/api/ask)로 질문을 보냅니다.
// Claude API 키는 Vercel 환경변수 ANTHROPIC_API_KEY 에만 저장되고, 방문자에게는 절대 보이지 않습니다.

const MODEL = process.env.CLAUDE_MODEL || "claude-haiku-5-5"; // 저렴하고 빠른 모델
const MAX_INPUT_CHARS = 12000;   // 한 번에 보낼 수 있는 글자 수 제한 (비용 보호)
const MAX_PER_IP_PER_HOUR = 30;  // 한 사람이 1시간에 보낼 수 있는 질문 수

const SYSTEM = `너는 '코리아 디스카운트 랩'의 리서치 도우미다. 한국 개인투자자에게 한국어로 답한다.
- 사용자가 보낸 데이터 안에서만 근거를 찾고, 근거(증권사·지표·피어 이름)를 문장 안에 밝힌다.
- 특정 종목의 매수·매도를 권유하지 않는다. 확률적이고 교육적인 표현을 쓴다.
- 주식과 관련 없는 요청에는 이 사이트의 용도를 짧게 안내하고 답하지 않는다.`;

const hits = new Map(); // 서버가 켜져 있는 동안만 기억하는 간단한 횟수 제한

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "POST만 받아요." });
  if (!process.env.ANTHROPIC_API_KEY) return res.status(503).json({ code: "not_configured", error: "AI 키가 설정되지 않았어요." });

  const ip = (req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "unknown";
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter((t) => now - t < 3600e3);
  if (recent.length >= MAX_PER_IP_PER_HOUR) return res.status(429).json({ code: "rate_limited", error: "잠시 후 다시 시도해 주세요." });
  recent.push(now);
  hits.set(ip, recent);

  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  const messages = Array.isArray(body.messages) ? body.messages.slice(-10) : [];
  const clean = messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_INPUT_CHARS) }));
  if (!clean.length || clean[clean.length - 1].role !== "user") return res.status(400).json({ error: "질문이 비어 있어요." });
  if (clean.reduce((n, m) => n + m.content.length, 0) > MAX_INPUT_CHARS * 2) return res.status(413).json({ error: "질문이 너무 길어요." });

  try {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({ model: MODEL, max_tokens: 800, system: SYSTEM, messages: clean }),
    });
    const j = await r.json();
    if (!r.ok) {
      console.error("Claude API 오류", r.status, j);
      return res.status(502).json({ code: "upstream", error: "AI 응답을 받지 못했어요." });
    }
    const text = (j.content || []).filter((c) => c.type === "text").map((c) => c.text).join("");
    return res.status(200).json({ text });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ code: "error", error: "AI 호출 중 오류가 났어요." });
  }
}
