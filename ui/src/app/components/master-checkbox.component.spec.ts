import { TestBed } from '@angular/core/testing';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { Checkable } from '../interfaces';

describe('SelectAllCheckboxComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SelectAllCheckboxComponent],
    }).compileComponents();
  });

  it('clicked sets checked on all list items', () => {
    const fixture = TestBed.createComponent(SelectAllCheckboxComponent);
    const list = new Map<string, Checkable>();
    list.set('u1', { checked: false });
    fixture.componentRef.setInput('id', 'queue');
    fixture.componentRef.setInput('list', list);
    fixture.componentInstance.selected = true;
    fixture.detectChanges();
    fixture.componentInstance.clicked();
    expect(list.get('u1')?.checked).toBe(true);
  });
});
