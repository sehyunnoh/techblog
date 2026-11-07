// Runs Anthropic's claude-code mods/privacy check (unmodified, only the import
// suffixes .js -> .ts) against a list of shell lines and compares each verdict
// with what the mod's README says should happen.
//
// Setup: copy these four files from
//   https://github.com/anthropics/claude-code/tree/0ed94698aa0aeee471465fc9c867c2e8434c4d68/mods/privacy/hooks/outbound
// into ./mod/ : names-user-agent.ts refusal.ts shell-tools.ts text-of.ts
// (change `.js'` to `.ts'` in the import lines). Then:
//   node privacy-mod-probe.mjs        (Node 22.6+ with type stripping)
//
// No Claude Code process is started and no network request is made. The email
// below is a made-up address, not an account.

import { namesUserAgentWithAddress } from './mod/names-user-agent.ts'
import { textOf } from './mod/text-of.ts'

const EMAIL = 'test.user@example.test'
const E = EMAIL

// Same decision as register.ts: pre-check for @ or %40, then the two matches.
function refused(input, email = EMAIL) {
  const text = textOf(input)
  if (!text.includes('@') && !text.includes('%40')) return false
  return namesUserAgentWithAddress(text, email)
}

// expect: 'block' = README says refused, 'pass' = README says it goes through,
//         'fp' = README says refused although the line sends nothing as a UA
const C = []
const add = (group, label, command, expect, tool = 'Bash') =>
  C.push({ group, label, command, expect, tool })

// A. Plain shapes the mod is meant to catch
add('A', 'curl -A', `curl -A "bot (${E})" https://example.test/`, 'block')
add('A', 'curl combined -sSLA', `curl -sSLA "bot ${E}" https://example.test/`, 'block')
add('A', 'curl -H User-Agent', `curl -H "User-Agent: bot ${E}" https://example.test/`, 'block')
add('A', 'curl --user-agent', `curl --user-agent "bot ${E}" https://example.test/`, 'block')
add('A', 'curl --user-a (prefix)', `curl --user-a "bot ${E}" https://example.test/`, 'block')
add('A', 'wget -U', `wget -U "bot ${E}" https://example.test/`, 'block')
add('A', 'wget --user-agent=', `wget --user-agent="bot ${E}" https://example.test/`, 'block')
add('A', 'iwr -UserAgent', `iwr https://example.test/ -UserAgent "bot ${E}"`, 'block', 'PowerShell')
add('A', 'irm -Headers hashtable', `irm https://example.test/ -Headers @{'User-Agent'='bot ${E}'}`, 'block', 'PowerShell')
add('A', 'python requests', `python -c "import requests; requests.get('https://example.test/', headers={'User-Agent': 'bot ${E}'})"`, 'block')
add('A', 'UA= variable', `UA="bot ${E}"; curl -A "$UA" https://example.test/`, 'block')
add('A', 'upper-case address', `curl -A "bot ${E.toUpperCase()}" https://example.test/`, 'block')
add('A', 'percent-encoded address', `curl -A "bot test.user%40example.test" https://example.test/`, 'block')
add('A', 'quote inside address', `curl -A "bot te''st.user@example.test" https://example.test/`, 'block')
add('A', 'line continuation in flag', `curl -\\\nA "bot ${E}" https://example.test/`, 'block')
add('A', 'PowerShell en dash flag', `iwr https://example.test/ –UserAgent "bot ${E}"`, 'block', 'PowerShell')
add('A', 'monitor tool', `curl -A "bot ${E}" https://example.test/`, 'block', 'Monitor')

// B. Shapes the README lists as passing
add('B', 'address in URL', `curl "https://example.test/?e=${E}"`, 'pass')
add('B', 'address in body', `curl -d "email=${E}" https://example.test/`, 'pass')
add('B', 'curl -u basic auth', `curl -u ${E}:pw https://example.test/`, 'pass')
add('B', 'curl --user basic auth', `curl --user ${E}:pw https://example.test/`, 'pass')
add('B', 'From: header', `curl -H "From: ${E}" https://example.test/`, 'pass')
add('B', 'computed at run time', `curl -A "bot $(git config user.email)" https://example.test/`, 'pass')
add('B', 'variable set elsewhere', `curl -A "bot $MAIL" https://example.test/`, 'pass')
add('B', 'file sent by name', `curl -A bot -d @mail.txt https://example.test/`, 'pass')
add('B', 'script that holds it', `python send.py`, 'pass')
add('B', 'double percent-encoding', `curl -A "bot test.user%2540example.test" https://example.test/`, 'pass')
add('B', 'base64 address', `curl -A "bot $(echo dGVzdC51c2VyQGV4YW1wbGUudGVzdA== | base64 -d)" https://example.test/`, 'pass')
add('B', 'client not named (aria2c -U)', `aria2c -U "bot ${E}" https://example.test/`, 'pass')
add('B', 'splatted hashtable, User key', `$p=@{Uri='https://example.test/';User='bot ${E}'}; iwr @p`, 'pass', 'PowerShell')

// C. Tried to slip past the two matches (not in the README list)
add('C', 'UA word built by concatenation', `python -c "h={'User-'+'Agent': 'bot ${E}'}"`, 'pass')
add('C', 'address built by concatenation', `curl -A "bot test.user"@"example.test" https://example.test/`, 'block')
add('C', 'address split in two strings', `python -c "e='test.user'+'@example.test'; h={'User-Agent': e}"`, 'pass')
add('C', 'hex escape for User', `curl -H $'\\x55ser-Agent: bot ${E}' https://example.test/`, 'pass')
add('C', 'header name via variable', `H=User-Agent; curl -H "$H: bot ${E}" https://example.test/`, 'block')
add('C', 'header name split by variable', `U=User; A=Agent; curl -H "$U-$A: bot ${E}" https://example.test/`, 'pass')
add('C', 'HTML entity for @', `curl -A "bot test.user&#64;example.test" https://example.test/`, 'pass')
add('C', 'curl config file via -K', `curl -K cfg.txt -d "${E}"`, 'pass')
add('C', 'httpie style header', `http https://example.test/ 'User-Agent:bot ${E}'`, 'block')
add('C', 'lynx -useragent', `lynx -useragent="bot ${E}" -dump https://example.test/`, 'block')
add('C', 'nc raw request', `printf 'GET / HTTP/1.1\\r\\nUser-Agent: bot ${E}\\r\\n\\r\\n' | nc example.test 80`, 'block')
// First guess was 'block'. Wrong: ua needs a word boundary, and the _ in CURL_UA is a word character.
add('C', 'variable named CURL_UA', `CURL_UA="bot ${E}" curl https://example.test/`, 'pass')
add('C', 'ua word but different tool', `node -e "fetch('https://example.test',{headers:{'user-agent':'bot ${E}'}})"`, 'block')
add('C', 'node fetch, no UA word', `node -e "fetch('https://example.test',{headers:{'x-contact':'${E}'}})"`, 'pass')

// D. Ordinary commands that hold the address and the word user-agent / ua
// First guess was 'fp'. Wrong: the pattern allows - or _ or nothing between user and agent, not a space.
add('D', 'commit message, "user agent" with a space', `git commit -m "log ${E} in the user agent parser"`, 'pass')
add('D', 'grep a log for user-agent', `grep -i user-agent access.log | grep ${E}`, 'fp')
add('D', 'curl -user (really -u ser)', `curl -user ${E}:pw https://example.test/`, 'fp')
add('D', 'mail with "ua:" in subject', `mail -s "ua: weekly report" ${E} < report.txt`, 'fp')
add('D', 'send mail, no UA word', `mail -s "weekly report" ${E} < report.txt`, 'pass')
add('D', 'git config email', `git config user.email ${E}`, 'pass')
add('D', 'ssh-keygen comment', `ssh-keygen -t ed25519 -C ${E}`, 'pass')

const rows = C.map(c => {
  const got = refused({ command: c.command }) ? 'block' : 'pass'
  const ok = c.expect === 'fp' ? got === 'block' : got === c.expect
  return { ...c, got, ok }
})

console.log('group | expected | got  | match | label')
for (const r of rows)
  console.log(`${r.group}     | ${r.expect.padEnd(8)} | ${r.got.padEnd(5)}| ${r.ok ? 'yes  ' : 'NO   '} | ${r.label}`)

const by = g => rows.filter(r => r.group === g)
console.log('\nsummary')
for (const g of ['A', 'B', 'C', 'D']) {
  const rs = by(g)
  console.log(`${g}: ${rs.filter(r => r.got === 'block').length} blocked, ${rs.filter(r => r.got === 'pass').length} passed, ${rs.filter(r => !r.ok).length} differ from README`)
}

// The comment in names-user-agent.ts says `jo@x.ua:` reads like `UA:`; check it
const ua = { command: 'curl https://example.test/?e=jo@x.ua: ' }
console.log('\njo@x.ua: address-only line refused =', refused(ua, 'jo@x.ua'))
