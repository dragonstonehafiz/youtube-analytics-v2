interface PaginationProps {
  page: number
  totalPages: number
  onChange: (page: number) => void
}

/** Previous / "Page x of y" / Next. Callers decide whether to render it for a single page. */
export default function Pagination({ page, totalPages, onChange }: PaginationProps) {
  return (
    <div className="pagination">
      <button type="button" className="btn-ghost" onClick={() => onChange(page - 1)} disabled={page <= 1}>
        Previous
      </button>
      <span className="pagination-info">Page {page} of {totalPages}</span>
      <button type="button" className="btn-ghost" onClick={() => onChange(page + 1)} disabled={page >= totalPages}>
        Next
      </button>
    </div>
  )
}
