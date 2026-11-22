export default function Pagination({ page, size, total, onChange }: {
  page: number; size: number; total: number; onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pagination">
      <span className="muted small">{total} résultat{total > 1 ? "s" : ""}</span>
      {pages > 1 && (
        <div className="row">
          <button className="btn btn-light btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>‹ Précédent</button>
          <span className="small">Page {page} / {pages}</span>
          <button className="btn btn-light btn-sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Suivant ›</button>
        </div>
      )}
    </div>
  );
}
