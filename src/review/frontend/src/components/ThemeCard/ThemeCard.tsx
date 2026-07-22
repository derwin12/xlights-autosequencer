import React from 'react';
import styles from './ThemeCard.module.css';

interface Theme {
  theme_id: string;
  name: string;
  description: string;
  accent: string;
  swatches: string[];
  default_for_kinds: string[];
  mood?: string;
  occasion?: string;
  genre?: string;
  editable?: boolean;
}

interface ThemeCardProps {
  theme: Theme;
  assigned?: boolean;
  assignedSections?: string[];
  onClick?: () => void;
  onEdit?: () => void;
}

export function ThemeCard({ theme, assigned = false, assignedSections = [], onClick, onEdit }: ThemeCardProps) {
  return (
    <div
      data-testid="theme-card"
      data-assigned={String(assigned)}
      className={`${styles.card} ${assigned ? styles.assigned : ''}`}
      style={{ borderColor: assigned ? theme.accent : 'transparent' }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
    >
      {/* Swatches row */}
      <div className={styles.swatchRow}>
        {theme.swatches.map((color, i) => (
          <div
            key={i}
            data-testid="swatch"
            className={styles.swatch}
            style={{ backgroundColor: color }}
          />
        ))}
      </div>

      {/* Name + ASSIGNED pill + edit btn */}
      <div className={styles.nameRow}>
        <span className={styles.name}>{theme.name}</span>
        {assigned && (
          <span className={styles.assignedPill}>Assigned</span>
        )}
        {theme.editable && onEdit && (
          <button
            className={styles.editBtn}
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            aria-label={`Edit ${theme.name}`}
          >
            ✎
          </button>
        )}
      </div>

      {/* Tags row */}
      {(theme.mood || theme.occasion || theme.genre) && (
        <div className={styles.tagRow}>
          {theme.mood && <span className={styles.tag}>{theme.mood}</span>}
          {theme.occasion && theme.occasion !== 'general' && (
            <span className={`${styles.tag} ${styles.tagOccasion}`}>{theme.occasion}</span>
          )}
          {theme.genre && theme.genre !== 'any' && (
            <span className={styles.tag}>{theme.genre}</span>
          )}
        </div>
      )}

      {/* Description */}
      <p className={styles.description}>{theme.description}</p>

      {/* Sections currently using this theme */}
      {assignedSections.length > 0 && (
        <div className={styles.sectionsRow} data-testid="assigned-sections">
          {assignedSections.map((label, i) => (
            <span key={i} className={styles.sectionChip}>{label}</span>
          ))}
        </div>
      )}
    </div>
  );
}
