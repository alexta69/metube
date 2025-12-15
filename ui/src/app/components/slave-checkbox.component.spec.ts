/* eslint-disable @angular-eslint/use-component-selector */
import { render, screen } from '@testing-library/angular';
import { SlaveCheckboxComponent } from './slave-checkbox.component';
import { MasterCheckboxComponent } from './master-checkbox.component';

describe('SlaveCheckboxComponent', () => {
  async function createSlaveCheckboxComponent(
    override: { template?: string; componentProperties?: Record<string, unknown> } = {},
  ) {
    override.template ||= `
      <app-slave-checkbox 
        [id]="'item1'" 
        [master]="masterCheckbox" 
        [checkable]="checkable" 
      />
    `;

    const mockMasterCheckbox = {
      id: () => 'master',
      selectionChanged: vi.fn(),
    } as unknown as MasterCheckboxComponent;

    const rendered = await render(override.template, {
      imports: [SlaveCheckboxComponent],
      componentProperties: {
        masterCheckbox: mockMasterCheckbox,
        checkable: { checked: false },
        ...override.componentProperties,
      },
    });

    return rendered;
  }

  it('should create the component', async () => {
    const { fixture } = await createSlaveCheckboxComponent();
    expect(fixture.componentInstance).toBeTruthy();
    expect(screen.getByRole('checkbox')).toBeDefined();
  });

  it('should render unchecked checkbox by default', async () => {
    await createSlaveCheckboxComponent();
    const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
  });

  it('should render checked checkbox when checkable.checked is true', async () => {
    await createSlaveCheckboxComponent({
      componentProperties: {
        checkable: { checked: true },
      },
    });
    const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
  });

  it('should have correct id attribute', async () => {
    const mockMasterCheckbox = {
      id: () => 'queue',
      selectionChanged: vi.fn(),
    } as unknown as MasterCheckboxComponent;

    await createSlaveCheckboxComponent({
      componentProperties: {
        masterCheckbox: mockMasterCheckbox,
        checkable: { checked: false },
      },
      template: `
        <app-slave-checkbox 
          [id]="'url123'" 
          [master]="masterCheckbox" 
          [checkable]="checkable" 
        />
      `,
    });

    const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
    expect(checkbox.id).toBe('queue-url123-select');
  });
});
