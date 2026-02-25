

clear all 
set more off
cap log close


*********************************************
// Figure 2. Group importance
*********************************************

	set obs 10
	g id = _n
	
	label def vars 10 "Financial development"  9 "Local demographics" 8 "Local politics" 7 "Human capital" 6 "Conflict"  5 "Public sector"  4 "Crime" 3 "Economic activity" 2 "Natural resources' exposure" 1 "Illicit activity" 
	
	g b = 0.729 if id == 1
	replace b = 0.694 if id == 2
	replace b = 0.685 if id == 3
	replace b = 0.683 if id == 4
	replace b = 0.677 if id == 5
	replace b = 0.668 if id == 6
	replace b = 0.650 if id == 7
	replace b = 0.649 if id == 8
	replace b = 0.625 if id == 9
	replace b = 0.552 if id == 10
	
	g ci_min = 0.675 if id == 1
	replace ci_min = 0.640 if id == 2
	replace ci_min = 0.634 if id == 3
	replace ci_min = 0.628 if id == 4
	replace ci_min = 0.622 if id == 5
	replace ci_min = 0.616 if id == 6
	replace ci_min = 0.593 if id == 7
	replace ci_min = 0.593 if id == 8
	replace ci_min = 0.569 if id == 9
	replace ci_min = 0.494 if id == 10

	
	g ci_max = 0.782 if id == 1
	replace ci_max = 0.750 if id == 2
	replace ci_max = 0.736 if id == 3
	replace ci_max = 0.739 if id == 4
	replace ci_max = 0.732 if id == 5
	replace ci_max = 0.721 if id == 6
	replace ci_max = 0.708 if id == 7
	replace ci_max = 0.705 if id == 8
	replace ci_max = 0.681 if id == 9
	replace ci_max = 0.611 if id == 10
	
	replace id = 11 - id
	levelsof id, local(levels)
	label val id vars 
	
	two (scatter id b ) (rcap  ci_max ci_min id, lc(gs12) fc(gs12) hor), ///
		ylabel(10 "Financial development"  9 "Local demographics" 8 "Local politics" 7 "Human capital" 6 "Conflict"  5 "Public sector"  4 "Crime" 3 "Economic activity" 2 "Natural resources" 1 "Illicit activity") ///
		scale(1.2) ytitle("", height(100)) legend(off) xlabel(0.5(0.1)0.8) xline(0.5, lcolor(grey))
	
	graph export "GroupImpAdd.pdf"		, replace

