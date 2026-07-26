import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Help } from '../../src/components/Help/Help';

describe('Help', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<Help open={false} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders FAQ entries and the Facebook group link when open', () => {
    render(<Help open onClose={vi.fn()} />);
    expect(screen.getByText(/help & faq/i)).toBeInTheDocument();
    expect(screen.getByText(/what's the overall workflow/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /join the facebook group/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /report an issue/i })).toBeInTheDocument();
  });

  it('calls onClose when the Close button is clicked', () => {
    const onClose = vi.fn();
    render(<Help open onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /^close$/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when clicking the backdrop', () => {
    const onClose = vi.fn();
    const { container } = render(<Help open onClose={onClose} />);
    const backdrop = container.firstChild as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
