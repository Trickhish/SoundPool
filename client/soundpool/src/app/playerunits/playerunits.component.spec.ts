import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PlayerunitsComponent } from './playerunits.component';

describe('PlayerunitsComponent', () => {
  let component: PlayerunitsComponent;
  let fixture: ComponentFixture<PlayerunitsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PlayerunitsComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PlayerunitsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
