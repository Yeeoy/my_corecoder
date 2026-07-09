// OpenAI 消息格式 → 前端 UI 卡片格式的转换。
//
// 后端持久化的是「喂给 LLM 的原始对话」(OpenAI 格式)，前端需要的是
// 「给人看的卡片」(UI 格式)。两者不是一回事，这个函数负责翻译：
//
//   OpenAI 格式(输入)                     UI 格式(输出)
//   {role:'system', ...}              →  (跳过，不显示)
//   {role:'user', content}            →  {type:'user', content}
//   {role:'assistant', content}       →  {type:'assistant', content}
//   {role:'assistant', tool_calls}    →  每个 tool_call 一张 {type:'tool', ...} 卡片
//   {role:'tool', tool_call_id, ...}  →  回填到对应 tool 卡片的 result
//
// 已知信息损失：OpenAI 格式不存 UI 元数据(如 duration)，所以从历史恢复的
// tool 卡片没有 duration。这是「只存 OpenAI 格式」的代价，前端 duration 是
// 可选显示，不会出错。

function parseToolArguments(rawArguments) {
  if (!rawArguments) return {}
  try {
    return JSON.parse(rawArguments)
  } catch {
    // 历史数据里可能有坏 JSON，兜底成空对象，别让整个转换崩掉
    return {}
  }
}

export function openaiToUiMessages(rawMessages) {
  if (!Array.isArray(rawMessages)) return []

  const uiMessages = []
  // tool_call id → 对应的 UI 卡片对象引用，用于回填 role:'tool' 的执行结果
  const toolCardById = {}

  for (const message of rawMessages) {
    const role = message.role

    if (role === 'system') {
      continue
    }

    if (role === 'user') {
      uiMessages.push({ type: 'user', content: message.content || '' })
      continue
    }

    if (role === 'assistant') {
      // assistant 可能同时带文字回答和工具调用；文字部分先产出一张卡片
      if (message.content) {
        uiMessages.push({ type: 'assistant', content: message.content })
      }
      // 每个 tool_call 产出一张 tool 卡片，并记下 id→卡片 供后续回填结果
      if (Array.isArray(message.tool_calls)) {
        for (const toolCall of message.tool_calls) {
          const card = {
            type: 'tool',
            name: toolCall.function?.name || 'unknown',
            arguments: parseToolArguments(toolCall.function?.arguments),
            status: 'done',
          }
          uiMessages.push(card)
          if (toolCall.id) {
            toolCardById[toolCall.id] = card
          }
        }
      }
      continue
    }

    if (role === 'tool') {
      // 不是新卡片，而是某张 tool 卡片的执行结果，按 tool_call_id 回填
      const card = toolCardById[message.tool_call_id]
      if (card) {
        card.result = message.content || ''
      }
      continue
    }
  }

  return uiMessages
}
