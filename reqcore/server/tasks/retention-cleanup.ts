import { defineTask } from 'nitropack/runtime/task'
import { runRetentionCleanup } from '../utils/retention-cleanup'

export default defineTask({
  meta: {
    name: 'retention-cleanup',
    description: 'Quarantine and erase candidates according to organization retention policies',
  },
  async run() {
    const result = await runRetentionCleanup({ source: 'scheduled_task' })
    return { result }
  },
})
