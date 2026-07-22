import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeCard } from '../../src/components/ThemeCard/ThemeCard';

const theme = {
  theme_id: 'peak-flash',
  name: 'Peak Flash',
  description: 'High-contrast whiteout hits.',
  accent: '#facc15',
  swatches: ['#facc15', '#fb923c', '#f5f5f0', '#0d0d10'],
  default_for_kinds: ['chorus'],
};

describe('ThemeCard', () => {
  it('renders theme name', () => {
    render(<ThemeCard theme={theme} />);
    expect(screen.getByText('Peak Flash')).toBeTruthy();
  });

  it('renders four swatches', () => {
    const { container } = render(<ThemeCard theme={theme} />);
    const swatches = container.querySelectorAll('[data-testid="swatch"]');
    expect(swatches).toHaveLength(4);
  });

  it('shows ASSIGNED pill when assigned', () => {
    render(<ThemeCard theme={theme} assigned={true} />);
    expect(screen.getByText(/assigned/i)).toBeTruthy();
  });

  it('does not show ASSIGNED pill when not assigned', () => {
    render(<ThemeCard theme={theme} assigned={false} />);
    expect(screen.queryByText(/assigned/i)).toBeNull();
  });

  it('has double-stroke border on assigned state', () => {
    const { container } = render(<ThemeCard theme={theme} assigned={true} />);
    const card = container.querySelector('[data-testid="theme-card"]') as HTMLElement;
    expect(card?.getAttribute('data-assigned')).toBe('true');
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<ThemeCard theme={theme} onClick={onClick} />);
    const card = screen.getByTestId('theme-card');
    fireEvent.click(card);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('shows a chip per section currently assigned this theme', () => {
    render(<ThemeCard theme={theme} assignedSections={['Intro', 'Chorus']} />);
    const row = screen.getByTestId('assigned-sections');
    expect(row.textContent).toContain('Intro');
    expect(row.textContent).toContain('Chorus');
  });

  it('renders no section-assignment row when no sections use this theme', () => {
    render(<ThemeCard theme={theme} assignedSections={[]} />);
    expect(screen.queryByTestId('assigned-sections')).toBeNull();
  });
});
