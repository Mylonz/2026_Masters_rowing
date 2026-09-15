# Boat Timeline Feature Specification

## Overview
This document defines the requirements for implementing a "Boat Timeline" feature similar to the existing "Rower Timeline" functionality in the 2026 Masters Nationals regatta portal. While the rower timeline shows a chronological view of races for individual rowers, the boat timeline will show the chronological sequence of races and activities for individual boats.

## Current Rower Timeline Functionality
The current rower timeline feature provides:
1. A modal dialog that shows all races for a selected rower on a given day
2. Visual indicators for consecutive races with tight turnaround times
3. Details about each race including time, event number, boat, oars assigned, crew, and special notes
4. Color-coded intervals between races indicating rest periods
5. Summary statistics showing total races, tight turnarounds, and critical turnarounds

## Proposed Boat Timeline Feature

### Core Functionality
1. **Boat Selection Interface**
   - Add a new button/link in the main navigation to access the boat timeline
   - Create a searchable dropdown/list of all boats in the fleet

2. **Boat Timeline View**
   - For each boat, display a chronological timeline of all scheduled activities
   - Include races where the boat is used
   - Include re-rigging activities
   - Include maintenance/check activities
   - Include transportation/loading activities

3. **Visual Timeline Components**
   - Vertical timeline showing chronological sequence of events
   - Color-coded segments representing different types of activities:
     * Racing (blue)
     * Re-rigging (orange)
     * Maintenance (gray)
     * Transportation (green)
   - Clear visual separation between days (Saturday/Sunday)

4. **Activity Details**
   - For races:
     * Time and event number
     * Crew list
     * Oar assignments
     * Special notes/rigging information
   - For re-rigging:
     * Time window
     * Required configuration change
     * Special instructions
   - For maintenance:
     * Scheduled time
     * Checklist items
   - For transportation:
     * Loading/unloading times
     * Trailer position

5. **Summary Information**
   - Total number of races for the boat
   - Total number of re-rigs required
   - Maintenance schedule summary
   - Critical time constraints

### Integration Points
1. **Data Sources**
   - `race_schedule.json` for race information
   - `regatta_load_plan.json` for boat specifications and maintenance requirements
   - Additional data about transportation schedules

2. **UI Integration**
   - Add navigation link in main header
   - Add boat filter to existing race schedule view
   - Consider quick-access buttons from boat names in race schedule

3. **Mobile Responsiveness**
   - Ensure timeline view works well on mobile devices
   - Adapt layout for smaller screens

### Technical Implementation
1. **New HTML Page**
   - Create `boat_timeline.html` similar to `race_schedule.html`
   - Reuse CSS styles where appropriate
   - Implement new JavaScript functionality for boat data processing

2. **Data Processing**
   - Extract boat-specific information from race schedule
   - Combine with fleet specification data
   - Calculate timing conflicts and dependencies
   - Generate maintenance schedule from checklists

3. **JavaScript Functions**
   - `getBoatSchedule(boatName)` - retrieve all activities for a boat
   - `computeBoatTurnarounds(boatSchedule)` - calculate time pressures
   - `renderBoatTimeline(boatSchedule)` - generate timeline UI
   - `filterByDay(schedule, day)` - filter activities by day

### User Experience
1. **Accessibility**
   - Ensure keyboard navigation works properly
   - Proper ARIA labels for timeline elements
   - Good color contrast for visual indicators

2. **Performance**
   - Efficient data processing to minimize load times
   - Lazy loading for large datasets if needed

3. **Error Handling**
   - Graceful handling of missing or incomplete data
   - Clear error messages when data cannot be loaded

## Benefits
1. Better planning for boat handlers and riggers
2. Improved visibility into boat utilization patterns
3. Enhanced coordination for trailer loading/unloading
4. Better identification of potential scheduling conflicts
5. Streamlined preparation for crews and support staff

## Future Enhancements
1. Integration with Google Calendar export
2. Print-friendly version for logistics teams
3. Notifications for upcoming maintenance deadlines
4. Conflict detection and alert system
5. Integration with actual vs planned timing data

## Dependencies
1. Existing data structures in `race_schedule.json` and `regatta_load_plan.json`
2. CSS framework already established in the project
3. JavaScript utilities for time formatting and data processing
