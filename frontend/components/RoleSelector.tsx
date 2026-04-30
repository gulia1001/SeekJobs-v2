'use client'

export const ROLES = [
  { label: 'Software Engineering', value: 'software_engineering' },
  { label: 'DevOps', value: 'devops' },
  { label: 'Analytics', value: 'analytics' },
  { label: 'Data / ML', value: 'data' },
  { label: 'QA', value: 'qa' },
  { label: 'Security', value: 'security' },
  { label: 'Design', value: 'design' },
  { label: 'Product', value: 'product' },
  { label: 'Management', value: 'management' },
]

interface Props {
  selected: string[]
  onChange: (roles: string[]) => void
}

export default function RoleSelector({ selected, onChange }: Props) {
  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((r) => r !== value))
    } else {
      onChange([...selected, value])
    }
  }

  return (
    <div className="role-selector">
      {ROLES.map((r) => (
        <button
          key={r.value}
          className={`role-tag${selected.includes(r.value) ? ' selected' : ''}`}
          onClick={() => toggle(r.value)}
          type="button"
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}
