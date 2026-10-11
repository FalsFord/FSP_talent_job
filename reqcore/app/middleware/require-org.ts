/**
 * Require-org middleware — redirects users without an active organization
 * to the org creation page. Must be used after the `auth` middleware.
 */
export default defineNuxtRouteMiddleware(async () => {
  const { data: session } = await authClient.useSession(useFetch)
  const localePath = useLocalePath()

  if (session.value && !session.value.session.activeOrganizationId) {
    return navigateTo(localePath('/onboarding/create-org'))
  }
})
