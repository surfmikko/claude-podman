#!/bin/bash
input=$(cat)
cwd=$(jq -r '.cwd // empty' <<<"$input")
branch=$(git -C "${cwd:-.}" branch --show-current 2>/dev/null)
project=$(cat "$HOME/.claude/project-name" 2>/dev/null)
jq -r --arg project "$project" --arg branch "$branch" '
  def pct: (. // 0 | floor);
  def k: (. // 0) as $n
    | if $n >= 1000 then "\($n / 1000 | floor)k" else "\($n | floor)" end;
  "\u001b[38;5;242m[\(.model.display_name // "?")]"
  + " C \(.context_window.total_input_tokens | k)"
  + (if .prompt_cache.hit_ratio != null
     then " | H \(.prompt_cache.hit_ratio * 100 | floor)%" else "" end)
  + (if .rate_limits.five_hour then
       " | S \(.rate_limits.five_hour.used_percentage | pct)%" else "" end)
  + (if .rate_limits.seven_day then
       " | W \(.rate_limits.seven_day.used_percentage | pct)%" else "" end)
  + (if $project != "" or $branch != "" then " |" else "" end)
  + (if $project != "" then " \($project)" else "" end)
  + (if $branch != "" then " (\($branch))" else "" end)
  + "\u001b[0m"
' <<<"$input"
