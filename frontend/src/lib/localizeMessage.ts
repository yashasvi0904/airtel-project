import type { Payment } from "./types";
import { tx } from "./tx";
import generated from "./locales/_patterns.json";

type Tr = (text: string, vars?: Record<string, string | number>) => string;

/**
 * Server messages are English sentences. Exact sentences are translated through the normal dictionary; sentences that embed a
 * number or name are matched by pattern and re-filled into the translated template. Anything unknown is shown as the server wrote it.
 */
const PATTERNS: [RegExp, string, string[]][] = [
  [/^Order placed for (\d+) product\(s\)\.$/, tx("Order placed for {n} product(s)."), ["n"]],
  [/^(UPI|Card|Net banking) payment of (₹[\d,.]+) started \(attempt (\d+)\)\.$/, tx("{method} payment of {amount} started (attempt {n})."), ["method", "amount", "n"]],
  [/^(₹[\d,.]+) received via (UPI|Card|Net banking) \((.*)\)\. Receipt (\S+?)\.( It arrived after the attempt timed out and was matched to this order\.)?$/, tx("{amount} received via {method} ({what}). Receipt {receipt}."), ["amount", "method", "what", "receipt"]],
  [/^(UPI|Card|Net banking) payment (failed|expired): (.*)$/, tx("{method} payment {state}: {why}"), ["method", "state", "why"]],
  [/^(UPI|Card|Net banking) payment was cancelled before completion\. No money was taken\.$/, tx("{method} payment was cancelled before completion. No money was taken."), ["method"]],
  [/^Technician visit booked for (\d{4}-\d{2}-\d{2}), (.*)\.$/, tx("Technician visit booked for {date}, {window}."), ["date", "window"]],
  [/^That OTP is incorrect\. (\d+) attempt\(s\) left\.$/, tx("That OTP is incorrect. {n} attempt(s) left."), ["n"]],
  [/^That file is larger than (\d+) MB/, tx("That file is larger than {n} MB. Please upload a smaller photo or scan."), ["n"]],
  [/^Please accept the terms/, tx("Please accept the terms to place the order"), []],
];

const compiled = (generated as { re: string; tpl: string; names: string[] }[]).map((p) => ({ re: new RegExp(p.re), tpl: p.tpl, names: p.names }));
const SENTENCES = /(?<=[.!?])\s+(?=[A-Z(])/;

/** Translate one sentence: exact dictionary hit, then a sentence pattern whose captured values are translated too. null = not known. */
function translateOne(message: string, tr: Tr, depth = 0): string | null {
  const direct = tr(message);
  if (direct !== message) return direct;
  const fillIn = (template: string, names: string[], m: RegExpMatchArray) => {
    const vars = Object.fromEntries(names.map((n, i) => {
      const v = m[i + 1];
      return [n, depth < 2 && /[A-Za-z]{3,}/.test(v) ? translateOne(v, tr, depth + 1) ?? v : v]; // "a WhatsApp channel for customers" inside "You asked for {p1}."
    }));
    return tr(template, vars);
  };
  for (const [re, template, names] of PATTERNS) {
    const m = message.match(re);
    if (m) return fillIn(template, names, m);
  }
  for (const p of compiled) {
    const m = message.match(p.re);
    if (m) return fillIn(p.tpl, p.names, m);
  }
  return null;
}

export function localizeMessage(message: string, tr: Tr): string {
  const one = translateOne(message, tr);
  if (one !== null) return one;
  // an engine message is often several sentences, or a ", "-joined list of labels: translate each part we know
  for (const split of [SENTENCES, /,\s+/]) {
    const parts = message.split(split);
    if (parts.length < 2) continue;
    let known = false;
    const out = parts.map((p) => { const t = translateOne(p, tr); if (t !== null) known = true; return t ?? p; });
    if (known) return out.join(split === SENTENCES ? " " : ", ");
  }
  return message;
}

/** Why a payment attempt failed, from its machine code (the English text is also the dictionary key). */
const FAILURE: Record<string, string> = {
  upi_declined: tx("The payment was declined in your UPI app. You can retry or choose another method."),
  insufficient_funds: tx("Your bank account has insufficient balance for this payment."),
  card_declined: tx("Your bank declined this card. Please try another card or payment method."),
  card_expired: tx("The bank reports this card as expired. Please use a different card."),
  card_not_supported: tx("This card is not accepted in the sandbox. Use one of the test cards shown below."),
  otp_failed: tx("Too many incorrect OTP attempts. Please start the payment again."),
  bank_declined: tx("Your bank declined the transaction. Please try again or use another method."),
  customer_abandoned: tx("You left the bank page before finishing. You can retry the payment."),
  expired: tx("The payment window expired and no money was taken. Please start the payment again."),
};

export function failureText(p: Pick<Payment, "failure_code" | "failure_message">, tr: Tr): string {
  if (p.failure_code && FAILURE[p.failure_code]) return tr(FAILURE[p.failure_code]);
  return p.failure_message ? localizeMessage(p.failure_message, tr) : tr("Please try again.");
}

/** What the customer should do right now, built from the payment's next-step type (not from the server's English sentence). */
export function nextActionText(p: Payment, tr: Tr): string {
  const na = p.next_action;
  if (!na) return tr("Processing...");
  switch (na.type) {
    case "upi_collect": return tr("We sent a payment request to {vpa}. Approve it in your UPI app.", { vpa: String(p.details.vpa ?? "") });
    case "upi_intent": return tr("Open your UPI app and complete the payment, or scan the QR code.");
    case "redirect": return tr("Taking you to {bank} to authorise the payment...", { bank: na.bank });
    case "card_otp": return tr("Enter the 6-digit OTP your bank sent to your registered mobile number.");
    default: return tr("Complete the payment in the secure window.");
  }
}
