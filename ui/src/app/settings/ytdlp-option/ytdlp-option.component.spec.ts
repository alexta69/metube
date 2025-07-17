import { ComponentFixture, TestBed } from '@angular/core/testing';

import { YtdlpOptionComponent } from './ytdlp-option.component';

describe('YtdlpOptionComponent', () => {
  let component: YtdlpOptionComponent;
  let fixture: ComponentFixture<YtdlpOptionComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [YtdlpOptionComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(YtdlpOptionComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
