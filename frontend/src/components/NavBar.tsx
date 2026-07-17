import { useNavigate } from 'react-router-dom'

interface NavBarProps {
  to?: string
  label?: string
}

export default function NavBar({ to, label = 'Back' }: NavBarProps) {
  const navigate = useNavigate()

  return (
    <button
      type="button"
      className="btn-back"
      onClick={() => (to ? navigate(to) : navigate(-1))}
    >
      ← {label}
    </button>
  )
}
