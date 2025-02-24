import { TestBed } from '@angular/core/testing';

import { LivefbService } from './livefb.service';

describe('LivefbService', () => {
  let service: LivefbService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(LivefbService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
