'use client'
import { useI18n, type MessageKey } from '@/lib/i18n'

export const ROLES = [
  'software_engineering', 'devops', 'analytics', 'data', 'qa', 'security', 'design', 'product', 'management',
]

interface Props {
  selected: string[]
  onChange: (roles: string[]) => void
}

export default function RoleSelector({ selected, onChange }: Props) {
  const { t } = useI18n()
  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((r) => r !== value) : [...selected, value])
  }

  return (
    <div className="role-selector">
      {ROLES.map((r) => (
        <button
          key={r}
          className={`role-tag${selected.includes(r) ? ' selected' : ''}`}
          onClick={() => toggle(r)}
          type="button"
          aria-pressed={selected.includes(r)}
        >
          {t(`cat.${r}` as MessageKey)}
        </button>
      ))}
    </div>
  )
}
