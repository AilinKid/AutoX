// Copyright 2026 AilinKid
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package domain

import "testing"

func TestProductionEligibilityRequiresSafetyContract(t *testing.T) {
	recommendation := Recommendation{
		Kind: RecommendationBinding,
		Validation: ValidationResult{
			Reproduced: true,
		},
		Safety: SafetyAssessment{
			Risk:               RiskLow,
			RequiresApproval:   true,
			Reversible:         true,
			RollbackStatement:  "DROP GLOBAL BINDING FOR ...",
			ProductionEligible: true,
		},
	}

	if err := recommendation.ValidateForProduction(); err != nil {
		t.Fatalf("expected valid production contract: %v", err)
	}
}

func TestProductionEligibilityRejectsUnreproducedAdvice(t *testing.T) {
	recommendation := Recommendation{
		Kind: RecommendationBinding,
		Safety: SafetyAssessment{
			RequiresApproval:   true,
			Reversible:         true,
			RollbackStatement:  "DROP GLOBAL BINDING FOR ...",
			ProductionEligible: true,
		},
	}

	if err := recommendation.ValidateForProduction(); err == nil {
		t.Fatal("unreproduced recommendation must not be production eligible")
	}
}
