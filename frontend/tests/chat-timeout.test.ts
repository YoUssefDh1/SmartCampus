import { afterEach, expect, it, vi } from "vitest";
import { chatApi } from "../src/lib/api/services";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("uses the configured chat timeout instead of the general API timeout", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn<typeof fetch>((_input, init) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener(
        "abort",
        () => reject(new DOMException("Aborted", "AbortError")),
        { once: true },
      );
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  const pendingReply = chatApi.sendMessage({ message: "Bonjour" });
  const signal = fetchMock.mock.calls[0]?.[1]?.signal;
  const chatTimeoutMs = Number(process.env.NEXT_PUBLIC_CHAT_TIMEOUT_MS ?? 130_000);
  expect(signal).toBeDefined();

  const beforeDefaultTimeout = Math.min(15_000, chatTimeoutMs - 1);
  await vi.advanceTimersByTimeAsync(beforeDefaultTimeout);
  expect(signal?.aborted).toBe(false);

  const beforeConfiguredTimeout = chatTimeoutMs - beforeDefaultTimeout - 1;
  if (beforeConfiguredTimeout > 0) {
    await vi.advanceTimersByTimeAsync(beforeConfiguredTimeout);
    expect(signal?.aborted).toBe(false);
  }

  const timedOutReply = expect(pendingReply).rejects.toMatchObject({ code: "TIMEOUT" });
  await vi.advanceTimersByTimeAsync(1);
  await timedOutReply;
  expect(signal?.aborted).toBe(true);
});
