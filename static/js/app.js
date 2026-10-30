/**
 * ABBAMAT - Control y Auditoría de Producción
 * Frontend Logic: Filtros dinámicos, Ordenamiento de Matriz, Timeline interactivo y navegación temporal
 */

// Función Global para Desplegar u Ocultar el Acordeón con Línea de Tiempo
window.toggleOperatorAccordion = function(operatorId, event) {
    if (event) {
        if (event.stopPropagation) {
            event.stopPropagation();
        }
        // Si el clic fue en un enlace o botón interno (salvo el botón toggle), no interceptar
        const isActionBtn = event.target.closest('.btn-toggle-timeline');
        const isOtherInteractive = event.target.closest('a') || (event.target.closest('button') && !isActionBtn);
        if (isOtherInteractive) {
            return;
        }
    }

    const accordionRow = document.getElementById('accordion-op-' + operatorId);
    const parentRow = document.getElementById('row-op-' + operatorId);
    if (!accordionRow) return;

    const toggleBtn = parentRow ? parentRow.querySelector('.btn-toggle-timeline') : null;
    const isHidden = window.getComputedStyle(accordionRow).display === 'none';

    if (!isHidden) {
        accordionRow.style.display = 'none';
        if (parentRow) parentRow.classList.remove('is-expanded');
        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', 'false');
            toggleBtn.classList.remove('active');
        }
    } else {
        accordionRow.style.display = 'table-row';
        if (parentRow) parentRow.classList.add('is-expanded');
        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', 'true');
            toggleBtn.classList.add('active');
        }
    }
};

document.addEventListener('DOMContentLoaded', function () {
    // 1. Selector de Fecha y Operario: Auto-submit al cambiar
    const dateInput = document.getElementById('topbar-date-input');
    if (dateInput) {
        dateInput.addEventListener('change', function () {
            const form = document.getElementById('date-filter-form');
            if (form) {
                form.submit();
            }
        });
    }

    const operarioSelect = document.getElementById('topbar-operario');
    if (operarioSelect) {
        operarioSelect.addEventListener('change', function () {
            const form = document.getElementById('date-range-filter-form');
            if (form) {
                form.submit();
            }
        });
    }

    // 2. Filtro instantáneo de búsqueda en la tabla de operarios (sincronizado con acordeón)
    const searchInput = document.getElementById('search-operator-input');
    if (searchInput) {
        searchInput.addEventListener('input', function (e) {
            const query = e.target.value.toLowerCase().trim();
            const rows = document.querySelectorAll('.operator-row');
            let visibleCount = 0;

            rows.forEach(function (row) {
                const name = row.getAttribute('data-name') || '';
                const id = row.getAttribute('data-id') || '';
                const match = name.toLowerCase().includes(query) || id.toLowerCase().includes(query);
                const accordion = document.getElementById(`accordion-op-${id}`);

                if (match) {
                    row.style.display = '';
                    visibleCount++;
                    if (row.classList.contains('is-expanded') && accordion) {
                        accordion.style.display = 'table-row';
                    }
                } else {
                    row.style.display = 'none';
                    if (accordion) {
                        accordion.style.display = 'none';
                    }
                }
            });

            const countEl = document.getElementById('visible-operator-count');
            if (countEl) {
                countEl.textContent = visibleCount;
            }
        });
    }

    // 3. Mini Tooltip Interactivo para bloques de Timeline
    const segments = document.querySelectorAll('.timeline-segment');
    segments.forEach(function (seg) {
        seg.addEventListener('mouseenter', function (e) {
            const title = seg.getAttribute('data-title');
            const desc = seg.getAttribute('data-desc');
            const time = seg.getAttribute('data-time');
            if (title) {
                seg.setAttribute('title', `${title}\n${desc || ''}\nHorario: ${time || ''}`);
            }
        });
    });

    // 4. Ordenamiento Dinámico e Interactivo de la Matriz de Producción
    const tableBody = document.querySelector('#tabla-operarios tbody');
    let currentSort = 'horas';
    let currentDir = 'desc';

    // Leer orden inicial desde la URL si existe
    const urlParams = new URLSearchParams(window.location.search);
    const initialOrden = (urlParams.get('orden') || 'horas_desc').toLowerCase();
    if (initialOrden === 'horas_asc') { currentSort = 'horas'; currentDir = 'asc'; }
    else if (initialOrden === 'cumplimiento_desc') { currentSort = 'cumplimiento'; currentDir = 'desc'; }
    else if (initialOrden === 'cumplimiento_asc') { currentSort = 'cumplimiento'; currentDir = 'asc'; }
    else if (initialOrden === 'nombre_asc') { currentSort = 'nombre'; currentDir = 'asc'; }
    else if (initialOrden === 'nombre_desc') { currentSort = 'nombre'; currentDir = 'desc'; }
    else { currentSort = 'horas'; currentDir = 'desc'; }

    function updateSortIndicators() {
        // Actualizar botones de toolbar
        document.querySelectorAll('.btn-sort-toggle').forEach(function (btn) {
            const btnSort = btn.getAttribute('data-sort');
            const icon = btn.querySelector('.sort-icon');
            if (btnSort === currentSort) {
                btn.classList.add('active');
                if (icon) {
                    icon.className = currentDir === 'desc' 
                        ? (btnSort === 'nombre' ? 'bi bi-sort-alpha-down-alt sort-icon' : 'bi bi-sort-down sort-icon')
                        : (btnSort === 'nombre' ? 'bi bi-sort-alpha-down sort-icon' : 'bi bi-sort-up sort-icon');
                }
            } else {
                btn.classList.remove('active');
                if (icon) {
                    icon.className = 'bi bi-arrow-down-up sort-icon';
                }
            }
        });

        // Actualizar encabezados de columna en la tabla
        document.querySelectorAll('.sortable-th').forEach(function (th) {
            const thSort = th.getAttribute('data-sort');
            const icon = th.querySelector('.th-sort-icon');
            if (thSort === currentSort) {
                th.classList.add('active-sort');
                if (icon) {
                    icon.className = currentDir === 'desc' 
                        ? (thSort === 'nombre' ? 'bi bi-sort-alpha-down-alt th-sort-icon' : 'bi bi-sort-down th-sort-icon')
                        : (thSort === 'nombre' ? 'bi bi-sort-alpha-down th-sort-icon' : 'bi bi-sort-up th-sort-icon');
                }
            } else {
                th.classList.remove('active-sort');
                if (icon) {
                    icon.className = 'bi bi-arrow-down-up th-sort-icon';
                }
            }
        });
    }

    function sortTable(criterio, direccion) {
        if (!tableBody) return;
        const rows = Array.from(tableBody.querySelectorAll('.operator-row'));
        if (rows.length === 0) return;

        rows.sort(function (a, b) {
            if (criterio === 'horas') {
                const valA = parseFloat((a.getAttribute('data-horas') || '0').replace(',', '.'));
                const valB = parseFloat((b.getAttribute('data-horas') || '0').replace(',', '.'));
                if (valA !== valB) {
                    return direccion === 'asc' ? valA - valB : valB - valA;
                }
                const cA = parseFloat((a.getAttribute('data-cumplimiento') || '0').replace(',', '.'));
                const cB = parseFloat((b.getAttribute('data-cumplimiento') || '0').replace(',', '.'));
                return direccion === 'asc' ? cA - cB : cB - cA;
            } else if (criterio === 'cumplimiento') {
                const valA = parseFloat((a.getAttribute('data-cumplimiento') || '0').replace(',', '.'));
                const valB = parseFloat((b.getAttribute('data-cumplimiento') || '0').replace(',', '.'));
                if (valA !== valB) {
                    return direccion === 'asc' ? valA - valB : valB - valA;
                }
                const hA = parseFloat((a.getAttribute('data-horas') || '0').replace(',', '.'));
                const hB = parseFloat((b.getAttribute('data-horas') || '0').replace(',', '.'));
                return direccion === 'asc' ? hA - hB : hB - hA;
            } else if (criterio === 'nombre') {
                const valA = (a.getAttribute('data-name') || '').toLowerCase();
                const valB = (b.getAttribute('data-name') || '').toLowerCase();
                if (valA < valB) return direccion === 'asc' ? -1 : 1;
                if (valA > valB) return direccion === 'asc' ? 1 : -1;
                return 0;
            }
            return 0;
        });

        // Reinsertar filas ordenadas en el DOM junto con su acordeón correspondiente
        rows.forEach(function (row) {
            tableBody.appendChild(row);
            const id = row.getAttribute('data-id');
            const accordion = document.getElementById(`accordion-op-${id}`);
            if (accordion) {
                tableBody.appendChild(accordion);
            }
        });

        currentSort = criterio;
        currentDir = direccion;
        updateSortIndicators();

        // Actualizar URL sin recargar
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('orden', `${criterio}_${direccion}`);
        window.history.replaceState({}, '', currentUrl);
    }

    // Escuchadores de botones de ordenamiento en la toolbar
    document.querySelectorAll('.btn-sort-toggle').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const sortField = this.getAttribute('data-sort');
            let nextDir = 'desc';
            if (currentSort === sortField) {
                nextDir = currentDir === 'desc' ? 'asc' : 'desc';
            } else if (sortField === 'nombre') {
                nextDir = 'asc';
            }
            sortTable(sortField, nextDir);
        });
    });

    // Escuchadores de encabezados de tabla clickeables
    document.querySelectorAll('.sortable-th').forEach(function (th) {
        th.addEventListener('click', function () {
            const sortField = this.getAttribute('data-sort');
            let nextDir = 'desc';
            if (currentSort === sortField) {
                nextDir = currentDir === 'desc' ? 'asc' : 'desc';
            } else if (sortField === 'nombre') {
                nextDir = 'asc';
            }
            sortTable(sortField, nextDir);
        });
    });

    // Inicializar indicadores
    updateSortIndicators();
});
