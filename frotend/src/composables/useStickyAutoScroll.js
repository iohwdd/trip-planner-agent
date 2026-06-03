import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const DEFAULT_RETRY_DELAYS = [16, 48, 120, 260, 520, 900, 1400];
const DEFAULT_BOTTOM_THRESHOLD = 28;

export function useStickyAutoScroll(source, options = {}) {
  const scrollRegion = ref(null);
  const scrollContent = ref(null);
  const bottomAnchor = ref(null);
  const stickToBottom = ref(true);
  const hasPinnedInitialContent = ref(false);

  const retryDelays = options.retryDelays || DEFAULT_RETRY_DELAYS;
  const bottomThreshold = options.bottomThreshold || DEFAULT_BOTTOM_THRESHOLD;

  let resizeObserver = null;
  let mutationObserver = null;
  let scrollFrame = null;
  let scrollRetryTimers = [];

  const requestFrame = (callback) => (
    typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame(callback)
      : window.setTimeout(() => callback(Date.now()), 16)
  );

  const cancelFrame = (handle) => {
    if (typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function") {
      window.cancelAnimationFrame(handle);
      return;
    }
    clearTimeout(handle);
  };

  function hasContent() {
    if (typeof options.hasContent === "function") {
      return options.hasContent();
    }
    return true;
  }

  function canStick(force = false) {
    if (force) {
      return true;
    }
    if (typeof options.stickWhen === "function" && options.stickWhen()) {
      return true;
    }
    return stickToBottom.value;
  }

  function clearScheduledScroll() {
    if (scrollFrame !== null) {
      cancelFrame(scrollFrame);
      scrollFrame = null;
    }
    for (const timer of scrollRetryTimers) {
      clearTimeout(timer);
    }
    scrollRetryTimers = [];
  }

  function isNearBottom() {
    const region = scrollRegion.value;
    if (!region) {
      return true;
    }
    const remaining = region.scrollHeight - region.scrollTop - region.clientHeight;
    return remaining <= bottomThreshold;
  }

  function syncStickyState() {
    stickToBottom.value = isNearBottom();
  }

  function setScrollToBottom() {
    const region = scrollRegion.value;
    if (!region) {
      return;
    }
    const bottomTop = Math.max(0, region.scrollHeight - region.clientHeight);
    if (typeof region.scrollTo === "function") {
      region.scrollTo({
        top: bottomTop,
        left: 0,
        behavior: "auto"
      });
    }
    region.scrollTop = bottomTop;
    stickToBottom.value = true;
    if (hasContent()) {
      hasPinnedInitialContent.value = true;
    }
  }

  function scheduleScrollToBottom({ force = false } = {}) {
    const shouldForceForInitialContent = hasContent() && !hasPinnedInitialContent.value;
    const effectiveForce = force || shouldForceForInitialContent;
    if (!canStick(effectiveForce)) {
      return;
    }
    clearScheduledScroll();
    nextTick(() => {
      scrollFrame = requestFrame(() => {
        setScrollToBottom();
        scrollFrame = null;
        scrollRetryTimers = retryDelays.map((delay) => setTimeout(() => {
          if (canStick(effectiveForce)) {
            setScrollToBottom();
          }
        }, delay));
      });
    });
  }

  function bindObservers() {
    const content = scrollContent.value;
    if (!content) {
      return;
    }

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => {
        scheduleScrollToBottom();
      });
      resizeObserver.observe(content);
    }

    if (typeof MutationObserver !== "undefined") {
      mutationObserver = new MutationObserver(() => {
        scheduleScrollToBottom();
      });
      mutationObserver.observe(content, {
        childList: true,
        characterData: true,
        subtree: true
      });
    }
  }

  function handleScroll() {
    syncStickyState();
  }

  onMounted(() => {
    bindObservers();
    scrollRegion.value?.addEventListener("scroll", handleScroll, { passive: true });
    scheduleScrollToBottom({ force: true });
  });

  onBeforeUnmount(() => {
    clearScheduledScroll();
    resizeObserver?.disconnect();
    mutationObserver?.disconnect();
    scrollRegion.value?.removeEventListener("scroll", handleScroll);
  });

  watch(
    source,
    () => {
      scheduleScrollToBottom({
        force: typeof options.forceOnChange === "function" ? options.forceOnChange() : false
      });
    },
    {
      flush: "post",
      immediate: true
    }
  );

  return {
    bottomAnchor,
    scrollContent,
    scrollRegion,
    scheduleScrollToBottom
  };
}
