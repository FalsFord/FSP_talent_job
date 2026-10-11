/**
 * useScrollFade — Intersection Observer composable for premium scroll-triggered animations.
 *
 * Returns a template ref. Attach it to any element with the `scroll-fade` CSS class.
 * When the element enters the viewport it receives the `is-visible` class, triggering
 * the CSS transition defined in main.css.
 *
 * Usage:
 *   const el = useScrollFade()
 *   <section ref="el" class="scroll-fade"> … </section>
 */
export function useScrollFade(options?: { threshold?: number; rootMargin?: string }) {
  const el = ref<HTMLElement | null>(null)

  onMounted(() => {
    if (!el.value) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target) // animate once
          }
        }
      },
      {
        threshold: options?.threshold ?? 0.15,
        rootMargin: options?.rootMargin ?? '0px 0px -40px 0px',
      },
    )

    observer.observe(el.value)

    onUnmounted(() => observer.disconnect())
  })

  return el
}

/**
 * useScrollFadeAll — observe multiple elements at once.
 * Call `register(el)` in a v-for / template ref function.
 */
export function useScrollFadeAll(options?: { threshold?: number; rootMargin?: string }) {
  const elements: HTMLElement[] = []
  let observer: IntersectionObserver | null = null

  function register(el: HTMLElement | ComponentPublicInstance | null) {
    if (!el) return
    const htmlEl = '$el' in el ? (el.$el as HTMLElement) : el
    if (htmlEl instanceof HTMLElement && !elements.includes(htmlEl)) {
      elements.push(htmlEl)
      observer?.observe(htmlEl)
    }
  }

  onMounted(() => {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer?.unobserve(entry.target)
          }
        }
      },
      {
        threshold: options?.threshold ?? 0.15,
        rootMargin: options?.rootMargin ?? '0px 0px -40px 0px',
      },
    )

    for (const el of elements) observer.observe(el)

    onUnmounted(() => observer?.disconnect())
  })

  return { register }
}
