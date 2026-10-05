export interface TabOption<T extends string> {
  value: T
  label: string
}

interface TabsProps<T extends string> {
  options: readonly TabOption<T>[]
  value: T
  onChange: (value: T) => void
  /** Extra classes for the row, e.g. `ts-subtabs` for a sub-tab row. */
  className?: string
}

export default function Tabs<T extends string>({ options, value, onChange, className }: TabsProps<T>) {
  return (
    <div className={className ? `tabs ${className}` : 'tabs'}>
      {options.map(option => (
        <button
          key={option.value}
          type="button"
          className={`tab${value === option.value ? ' active' : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
