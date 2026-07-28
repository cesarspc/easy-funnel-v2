# Requirements Document

## Introduction

The COD Commerce Platform is a lightweight, cloud-hosted commerce system for low-ticket physical products sold by cash on delivery in Colombia. Version 1 replaces the currently used subset of Shopify, GemPages, and the Realist form application with product administration, banner-based product landings, COD order capture, fraud controls, order administration, analytics, and CSV export.

The guiding principle for version 1 is: every feature must map directly to the flow **banner landing → CTA → COD form → fraud check → order in admin**. A capability that does not serve this flow is outside version 1.

Version 1 explicitly excludes online payment gateways and native payment checkout; Shopify Markets; multi-currency storefronts; multi-language storefronts; drag-and-drop visual page building; theme marketplaces; theme customization systems; third-party application marketplaces; subscriptions; recurring billing; multi-warehouse inventory routing; point-of-sale and in-person sales; external content delivery networks; paid page-builder software as a service; server-side rendering; administrator fraud notifications; day-one database connection pooling; and horizontal scaling.

## Glossary

- **COD_Commerce_Platform**: The complete version 1 system described by this document.
- **Complete_COD_Flow**: The integrated end-to-end sequence from a public banner Landing through CTA activation, COD_Form submission, synchronous Fraud_Check evaluation, Order persistence, and Order availability in the Admin_Dashboard.
- **COD**: Cash on delivery, in which payment is collected when a physical order is delivered.
- **Administrator**: The single authenticated dashboard role available in the MVP.
- **Admin_Dashboard**: The private browser interface used by the Administrator.
- **Product_Catalog**: The subsystem that stores and manages Product records.
- **Product**: A sellable physical item with an identifier, name, SKU, price, description, status, and creation timestamp.
- **SKU**: A merchant-assigned stock-keeping identifier for a Product.
- **Active_Product**: A Product whose status permits public access to the associated published Landing.
- **Paused_Product**: A Product whose status prevents public access without deleting Product data.
- **Retired_Product**: A soft-deleted Product excluded from normal catalog operations and public access while retained for historical Order and audit references.
- **Soft_Deletion**: A lifecycle change that retires a record without physically erasing the record or historical references.
- **Landing_Service**: The subsystem that manages and presents product-specific Landing records.
- **Landing**: The single banner-based sales page associated with a Product.
- **Published_Landing**: A Landing available through the public product URL when the associated Product is active.
- **Draft_Landing**: A Landing unavailable through the public product URL.
- **Slug**: A unique URL-safe identifier used in `/p/{slug}`.
- **Banner**: An ordered Landing image with alternative text and generated Image_Variants.
- **CTA**: A call-to-action purchase control that opens the COD_Form.
- **CTA_Placement_Mode**: One of three configurations: after every Banner, after every configured number of Banners, or at configured fixed Banner positions.
- **COD_Form**: The public form that captures a COD order request.
- **Inline_Mode**: A COD_Form presentation that expands within a Landing.
- **Modal_Mode**: A COD_Form presentation that opens in an overlaid dialog.
- **Colombian_Phone_Number**: A Colombian mobile number normalized to `+57` followed by 10 digits, where the national number begins with `3`; input may contain the `+57` or `57` country code and may contain spaces, hyphens, or parentheses before normalization.
- **Order_Service**: The subsystem that validates, records, queries, updates, and exports Order records.
- **Order**: A submission containing the Product, Landing, customer name, phone, department, city, address, quantity, status, IP address, user agent, Fraud_Flags, and creation timestamp.
- **Valid_Order_Submission**: A COD_Form submission that satisfies the field and format constraints in Requirement 5.
- **Normal_Order**: An Order that passes every enabled Fraud_Check and enters `pending` status.
- **Flagged_Order**: An Order stored with `flagged_fraud` status after one or more Fraud_Check results trigger.
- **Order_Status**: One of `pending`, `confirmed`, `shipped`, `delivered`, `cancelled`, or `flagged_fraud`.
- **Fraud_Prevention_Service**: The server-side subsystem that evaluates each Valid_Order_Submission before Order classification.
- **Fraud_Check**: Duplicate detection, Manual_Blacklist matching, Rate_Limit evaluation, or GeoIP_Rule evaluation.
- **Fraud_Flag**: A stored machine-readable explanation identifying a triggered Fraud_Check and relevant rule result.
- **Duplicate_Window**: The configurable number of preceding hours inspected by duplicate detection, defaulting to 24 hours.
- **Duplicate_Match_Fields**: The Administrator-selected Order fields used together for duplicate detection, defaulting to phone number and IP address.
- **Manual_Blacklist**: The Administrator-managed set of flagged phone numbers and IP addresses, including a reason and creation timestamp for each entry.
- **Manual_Blacklist_Validity_Requirements**: A supported entry type of phone number or IP address; a Colombian_Phone_Number normalized according to this document for a phone entry or a syntactically valid canonical IPv4 or IPv6 address for an IP entry; and a trimmed reason containing from 1 through 500 characters.
- **Rate_Limit**: A configurable maximum number of submission attempts permitted within a rolling window, applied independently to submission attempts by phone number and IP address; a Rate_Limit triggers only when the count including the current attempt exceeds the configured maximum.
- **GeoIP_Database**: A periodically updated, self-hosted mapping from IP addresses to countries or regions.
- **GeoIP_Rule**: A configurable rule that has an action named `flag` or `block` and identifies submissions from selected countries or regions; both actions produce a reviewable Flagged_Order in version 1.
- **Fraud_Configuration**: The editable Duplicate_Window, Duplicate_Match_Fields, Rate_Limit thresholds, and GeoIP_Rules.
- **Image_Pipeline**: The subsystem that stores source images, removes metadata, creates responsive image formats, and cleans orphaned files.
- **Upload_Pipeline_Outage**: A period in which the Image_Pipeline cannot safely accept and complete new image uploads because the upload capability is unavailable or under maintenance.
- **Supported_Source_Image**: A decodable JPEG, PNG, or WebP file satisfying the Image_Validation_Limits.
- **Image_Validation_Limits**: Source-image width from 480 through 8,000 pixels, height from 1 through 8,000 pixels, total width multiplied by height no greater than 40,000,000 pixels, and encoded file size no greater than 10 MiB.
- **MiB**: 1,048,576 bytes.
- **Image_Variant**: A generated WebP or JPEG image at one of the configured responsive widths.
- **EXIF_Metadata**: Embedded image metadata that can contain device, timestamp, or location information.
- **R2_Image_Storage**: Persistent object storage provided by Cloudflare R2, accessed by the backend for source images and Image_Variants.
- **Opaque_Image_Identifier**: A platform-generated storage identifier that contains no client filename or other client-controlled path content and does not reveal a predictable storage sequence.
- **Orphaned_Image**: A stored source image or Image_Variant that has no live or historical Banner reference and is not part of an in-progress image operation.
- **Analytics_Service**: The subsystem that records Landing views and CTA clicks and calculates dashboard metrics.
- **Conversion_Rate**: The number of Orders attributed to a Landing divided by the number of recorded views for that Landing over the same selected period, expressed as zero when the view count is zero.
- **Flagged_Fraud_Rate**: The number of Flagged_Orders divided by all Orders over the same selected period, expressed as zero when the Order count is zero.
- **CSV_Export**: A comma-separated-value file containing Order data for courier or fulfillment handoff.
- **Authentication_Service**: The subsystem that verifies Administrator credentials and issues and validates JWT-based sessions.
- **Operational_Read_Interface**: The specifically documented, authenticated, read-only interface outside the normal Administrator business API, limited to service health state, deployed application version, and success or failure status with timestamps for backup, GeoIP update, and image cleanup operations.
- **Non_Sensitive_Operational_Information**: The information defined for the Operational_Read_Interface, excluding customer data, credentials, JWT values, database connection data, filesystem paths, request payloads, application log content, and diagnostic stack details.
- **JWT**: A signed JSON Web Token used to represent an Administrator session.
- **SPA**: A statically built single-page web application that performs browser-side routing.
- **API**: The HTTP application programming interface exposed by the backend.
- **Cloudflare_Pages**: The static hosting platform that builds and serves the frontend SPA.
- **Cloudflare_DNS**: The DNS and request-routing layer that directs public traffic to Cloudflare Pages and to the Koyeb-hosted backend.
- **Koyeb**: The managed container platform that runs the backend as a single FastAPI Docker container.
- **Cloud_Deployment**: The cloud-native deployment of the COD_Commerce_Platform across Cloudflare Pages, Cloudflare DNS, Koyeb, PostgreSQL, Upstash_Redis, and R2_Image_Storage.
- **PostgreSQL**: The relational database, hosted as managed Neon PostgreSQL, used for durable application records.
- **Prisma_ORM**: The object-relational mapping layer through which the backend accesses PostgreSQL.
- **Upstash_Redis**: Managed Redis used for rate limiting, fraud counters, temporary state, and caching data.
- **TLS**: Transport Layer Security for encrypted HTTP connections.
- **LCP**: Largest Contentful Paint measured for a public Landing using a mobile 4G network profile.
- **4G_Profile**: A repeatable browser performance-test profile configured with 4G-class latency and bandwidth.
- **MVP**: The low-volume, cloud-native version 1 release.
- **External_CDN**: A third-party content delivery network outside the Cloud_Deployment request path.
- **SaaS**: Software operated by an external vendor as a hosted service.
- **Domain_Validation_Limits**: The Product, Banner, image, customer, quantity, price, and stored user-agent limits stated in Requirements 2 through 5.
- **Audit_History**: Records of security events and Administrator mutations containing the actor, action, target, result, and timestamp.

## Requirements

### Requirement 1: Version 1 Scope and Platform Constraints

**User Story:** As a platform owner, I want a constrained COD-focused MVP, so that implementation effort serves the Colombian COD sales flow.

#### Acceptance Criteria

1. THE COD_Commerce_Platform SHALL implement the Complete_COD_Flow as one integrated end-to-end capability rather than as disconnected components.
2. THE COD_Commerce_Platform SHALL limit version 1 commerce transactions to COD.
3. THE COD_Commerce_Platform SHALL exclude online payment gateways and native payment checkout from version 1.
4. THE COD_Commerce_Platform SHALL exclude Shopify Markets, multi-currency storefronts, and multi-language storefronts from version 1.
5. THE COD_Commerce_Platform SHALL exclude drag-and-drop page building, theme marketplaces, and theme customization systems from version 1.
6. THE COD_Commerce_Platform SHALL exclude third-party application marketplaces, subscriptions, and recurring billing from version 1.
7. THE COD_Commerce_Platform SHALL exclude multi-warehouse inventory routing, point-of-sale sales, and in-person sales from version 1.
8. THE COD_Commerce_Platform SHALL exclude External_CDN and paid page-builder SaaS dependencies from version 1.
9. THE COD_Commerce_Platform SHALL provide the public Landing and Admin_Dashboard as a React and Vite SPA using React Router.
10. THE COD_Commerce_Platform SHALL provide the API through FastAPI and store durable application records in PostgreSQL through Prisma_ORM.
11. THE COD_Commerce_Platform SHALL process images with Pillow and store source images and Image_Variants in R2_Image_Storage.
12. THE COD_Commerce_Platform SHALL deploy the SPA to Cloudflare_Pages and the API as a single backend Docker container to Koyeb, connected to PostgreSQL, Upstash_Redis, and R2_Image_Storage.
13. THE COD_Commerce_Platform SHALL use JWT-based Administrator sessions.
14. THE COD_Commerce_Platform SHALL exclude server-side Landing rendering from version 1.
15. THE COD_Commerce_Platform SHALL present fraud review through the Admin_Dashboard without version 1 email, Telegram, or WhatsApp notifications.
16. THE COD_Commerce_Platform SHALL operate as a low-volume MVP without day-one database connection pooling, multi-node orchestration, or horizontal scaling.
17. THE COD_Commerce_Platform SHALL exclude runtime dependencies on external image transformation, analytics, geolocation, and page-building services.

### Requirement 2: Product Management

**User Story:** As an Administrator, I want to manage products and availability, so that each sales Landing is attached to a controlled catalog item.

#### Acceptance Criteria

1. WHEN an Administrator submits a Product creation request whose required fields and supplied values satisfy every applicable Product validation requirement, THE Product_Catalog SHALL atomically store the Product identifier, name, SKU, price, description, status, and creation timestamp only after all validation succeeds.
2. WHEN an Administrator creates a Product, THE Product_Catalog SHALL validate and accept a trimmed name containing from 1 through 160 characters.
3. WHEN an Administrator creates a Product, THE Product_Catalog SHALL validate and accept a description containing from 0 through 5,000 characters.
4. WHEN an Administrator creates a Product, THE Product_Catalog SHALL validate and accept a decimal price from 0.01 through 999,999,999.99 with no more than two fractional decimal places.
5. WHEN the Product_Catalog creates a Product, THE Product_Catalog SHALL accept a non-empty SKU only when no non-retired or Retired_Product record has the same SKU.
6. WHEN the Product_Catalog creates a Product, THE Product_Catalog SHALL assign `paused` status unless the Administrator explicitly selects `active` status.
7. WHEN the Product_Catalog creates a Product, THE Landing_Service SHALL associate exactly one Draft_Landing with the Product.
8. WHEN an Administrator requests an existing non-retired Product, THE Product_Catalog SHALL return the stored Product fields and associated Landing reference.
9. WHEN an Administrator submits valid changes to a non-retired Product, THE Product_Catalog SHALL persist the changed values and retain the Product identifier and creation timestamp.
10. IF a Product creation request contains a missing required field or any supplied value fails an applicable Product validation requirement, including an out-of-range name, an out-of-range description, an invalid price, an unsupported status, or a duplicate SKU, THEN THE Product_Catalog SHALL reject the request with a field-specific validation error without storing a Product or associated Draft_Landing.
11. WHEN an Administrator pauses an Active_Product, THE Landing_Service SHALL make the associated Landing unavailable through the public product URL without deleting Product, Landing, Banner, or Order data.
12. WHEN an Administrator activates a Paused_Product with a Published_Landing, THE Landing_Service SHALL make the associated Landing available through the public product URL.
13. WHEN an Administrator confirms Product deletion, THE Product_Catalog SHALL apply Soft_Deletion and classify the Product as a Retired_Product.
14. WHEN the Product_Catalog retires a Product, THE Landing_Service SHALL make the associated Landing unavailable through the public product URL and exclude the Product from normal catalog operations.
15. WHEN the Product_Catalog retires a Product, THE Product_Catalog SHALL preserve the Product, associated Landing, associated Banner references, historical Orders, Fraud_Flags, attribution data, and Audit_History.
16. IF an Administrator requests physical erasure through the Product deletion operation, THEN THE Product_Catalog SHALL perform Soft_Deletion instead of destructive erasure.
17. IF an Administrator requests activation or editing of a Retired_Product through normal catalog operations, THEN THE Product_Catalog SHALL reject the request without changing the Retired_Product.
18. WHEN the Admin_Dashboard lists Products for normal catalog operations, THE Product_Catalog SHALL exclude Retired_Product records from the default result.
19. WHEN an Administrator requests activation of a Paused_Product, THE Product_Catalog SHALL change the Product status to `active`.
20. IF an Administrator requests activation of an Active_Product or a Retired_Product, THEN THE Product_Catalog SHALL reject the activation without changing Product, Landing, Banner, or Order data.
21. IF the Admin_Dashboard cannot display retirement wording or fails while presenting or confirming Product retirement, THEN THE Product_Catalog SHALL still enforce Soft_Deletion and the preservation requirements in criterion 15 and SHALL NOT destructively erase Product, Landing, Banner, Order, Fraud_Flag, attribution, or Audit_History data.
22. IF a Product update request contains a missing required field, an out-of-range name, an out-of-range description, an invalid price, or a duplicate SKU, THEN THE Product_Catalog SHALL reject the request with a field-specific validation error without changing the stored Product or associated Landing.

### Requirement 3: Landing and Banner Management

**User Story:** As an Administrator, I want to compose a product Landing from ordered banners and configurable CTAs, so that I can publish mobile-first sales pages without a visual page builder.

#### Acceptance Criteria

1. WHEN an Administrator assigns a Slug containing only lowercase letters, digits, and single hyphens between non-hyphen characters, THE Landing_Service SHALL persist the Slug for the route `/p/{slug}`.
2. IF an Administrator submits an empty Slug, a malformed Slug, or a Slug assigned to another live or retired Landing, THEN THE Landing_Service SHALL reject the Slug with a field-specific validation error.
3. WHEN an Administrator uploads a Supported_Source_Image with trimmed alternative text containing from 1 through 200 characters, THE Landing_Service SHALL create a Banner containing the alternative text and an order index.
4. IF an Administrator submits Banner alternative text containing fewer than 1 character or more than 200 characters after trimming, THEN THE Landing_Service SHALL reject the Banner mutation with a field-specific validation error.
5. WHEN an Administrator adds a Banner to a Landing containing fewer than 15 Banners, THE Landing_Service SHALL place the Banner at a unique position in the ordered sequence.
6. IF an Administrator attempts to add a sixteenth Banner to a Landing, THEN THE Landing_Service SHALL reject the upload without changing the ordered Banner sequence.
7. WHEN an Administrator changes a Banner position, THE Landing_Service SHALL present all Landing Banners in contiguous ascending order without duplicate positions.
8. WHEN an Administrator removes a Banner, THE Landing_Service SHALL remove the Banner from the ordered Landing sequence and close the resulting position gap.
9. WHEN an Administrator selects the CTA_Placement_Mode after every Banner, THE Landing_Service SHALL persist the selected mode without an interval or fixed-position value.
10. WHEN an Administrator selects the CTA_Placement_Mode after every configured number of Banners, THE Landing_Service SHALL require and persist an integer interval from 1 through 15.
11. WHEN an Administrator selects the CTA_Placement_Mode using fixed Banner positions, THE Landing_Service SHALL require and persist a non-empty set of unique positions within the current Banner sequence.
12. WHERE the CTA_Placement_Mode is after every Banner, THE Landing_Service SHALL render one CTA after each Banner.
13. WHERE the CTA_Placement_Mode is after every configured number of Banners, THE Landing_Service SHALL render a CTA after each completed configured interval.
14. WHERE the CTA_Placement_Mode uses fixed Banner positions, THE Landing_Service SHALL render CTAs only after the configured positions.
15. IF a CTA interval or fixed position falls outside the valid configuration range, THEN THE Landing_Service SHALL reject the configuration without replacing the active CTA configuration.
16. WHEN an Administrator selects Inline_Mode or Modal_Mode, THE Landing_Service SHALL persist the selected COD_Form presentation for the Landing.
17. WHEN a visitor activates a CTA, THE Landing_Service SHALL open the COD_Form using the Landing’s configured presentation.
18. WHERE a Landing uses Modal_Mode, THE Landing_Service SHALL move keyboard focus into the opened COD_Form and return keyboard focus to the activating CTA when the visitor closes the COD_Form.
19. WHEN an Administrator requests publication of a Landing containing from 1 through 15 valid Banners and a valid CTA configuration, THE Landing_Service SHALL change the Landing to published status.
20. IF an Administrator requests publication of a Landing containing zero Banners or an invalid CTA configuration, THEN THE Landing_Service SHALL reject publication with a field-specific validation error.
21. WHILE a Landing has draft status, THE Landing_Service SHALL return a not-found response for unauthenticated requests to the public product URL.
22. WHILE a Product is paused or retired, THE Landing_Service SHALL return a not-found response for unauthenticated requests to the associated public product URL.
23. WHEN an unauthenticated visitor requests an Active_Product’s Published_Landing by Slug, THE Landing_Service SHALL render the Banners in stored order with the configured CTAs.
24. IF an unauthenticated visitor requests an unknown, draft, paused, or retired Landing Slug, THEN THE Landing_Service SHALL return the same not-found response without disclosing private Landing data.
25. WHEN a public Landing containing from 1 through 15 Banners is tested at supported mobile viewport widths, THE Landing_Service SHALL render every Banner and configured CTA without horizontal overflow or overlapping controls.
26. WHEN a public Landing is measured using the 4G_Profile with production image settings, THE Landing_Service SHALL produce an LCP below 2.5 seconds.

### Requirement 4: Self-Hosted Image Processing

**User Story:** As an Administrator, I want uploaded banners optimized on the platform, so that mobile Landings load efficiently without an external image service.

#### Acceptance Criteria

1. WHEN an Administrator uploads a JPEG, PNG, or WebP file, THE Image_Pipeline SHALL decode the file before classifying the file as a Supported_Source_Image.
2. WHEN the Image_Pipeline validates a source image, THE Image_Pipeline SHALL accept a width from 480 through 8,000 pixels.
3. WHEN the Image_Pipeline validates a source image, THE Image_Pipeline SHALL accept a height from 1 through 8,000 pixels.
4. WHEN the Image_Pipeline validates a source image, THE Image_Pipeline SHALL accept a total width multiplied by height no greater than 40,000,000 pixels.
5. WHEN the Image_Pipeline validates a source image, THE Image_Pipeline SHALL accept an encoded file size no greater than 10 MiB.
6. IF any source-image validation fails, including because an upload has a disallowed media type, cannot be decoded, has a width outside 480 through 8,000 pixels, has a height outside 1 through 8,000 pixels, exceeds 40,000,000 total pixels, or exceeds 10 MiB, THEN THE Image_Pipeline SHALL reject the upload with a field-specific validation error before public availability.
7. WHEN an Administrator uploads a Supported_Source_Image, THE Image_Pipeline SHALL store the source image in R2_Image_Storage.
8. WHEN the Image_Pipeline accepts a Supported_Source_Image, THE Image_Pipeline SHALL remove EXIF_Metadata before creating public image files.
9. WHEN the Image_Pipeline accepts a Supported_Source_Image, THE Image_Pipeline SHALL generate WebP and JPEG Image_Variants at configured widths that include 480, 768, 1,200, and 1,600 pixels without generating a width greater than the source width.
10. WHEN the Image_Pipeline creates an Image_Variant, THE Image_Pipeline SHALL preserve the source aspect ratio within image-encoding rounding tolerance.
11. WHEN the Image_Pipeline completes every required variant, THE Image_Pipeline SHALL associate the source image and Image_Variants with the Banner as one completed upload operation.
12. IF the Image_Pipeline cannot store the source image or complete every required variant, THEN THE Image_Pipeline SHALL reject the upload, remove partial files, and omit a usable Banner association.
13. WHEN the Landing_Service renders a Banner, THE Landing_Service SHALL provide responsive image candidates, intrinsic dimensions, and a JPEG fallback.
14. WHEN the Landing_Service renders a Banner below the initial viewport content, THE Landing_Service SHALL mark the Banner image for browser lazy loading.
15. WHEN Cloudflare serves an Image_Variant from R2_Image_Storage, THE Cloud_Deployment SHALL provide an immutable long-duration cache policy for the versioned Image_Variant URL.
16. WHEN scheduled image cleanup identifies an Orphaned_Image, THE Image_Pipeline SHALL remove the Orphaned_Image and record the cleanup result.
17. IF scheduled image cleanup encounters a missing Orphaned_Image file, THEN THE Image_Pipeline SHALL record the missing-file result and continue processing remaining Orphaned_Image records.
18. WHILE a Product, Landing, Banner, or Order retains a live or historical image reference, THE Image_Pipeline SHALL exclude the referenced file from orphan cleanup.
19. THE Image_Pipeline SHALL serve public image files from R2_Image_Storage without an External_CDN or image SaaS.
20. WHILE an Upload_Pipeline_Outage is active, THE Cloud_Deployment SHALL continue serving already-generated Image_Variants from R2_Image_Storage.
21. WHILE an Upload_Pipeline_Outage is active, WHEN an Administrator submits a new image upload, THE Image_Pipeline SHALL reject the upload with a non-sensitive unavailable response, remove partial files, and omit a usable Banner association.
22. WHILE an Upload_Pipeline_Outage is active, THE COD_Commerce_Platform SHALL keep image delivery within R2_Image_Storage without activating an External_CDN, external image service, or SaaS fallback.

### Requirement 5: COD Order Capture and Validation

**User Story:** As a Colombian customer, I want to submit delivery details for a COD purchase, so that the merchant can fulfill the order without online payment.

#### Acceptance Criteria

1. WHEN a visitor opens a COD_Form, THE Order_Service SHALL request full name, Colombian_Phone_Number, department, city, address, and quantity.
2. WHEN the COD_Form validates a customer full name, THE COD_Form SHALL accept a trimmed value containing from 2 through 120 characters.
3. WHEN the COD_Form validates a department or city, THE COD_Form SHALL accept a trimmed value containing from 2 through 100 characters.
4. WHEN the COD_Form validates an address, THE COD_Form SHALL accept a trimmed value containing from 5 through 250 characters.
5. WHEN the COD_Form validates quantity, THE COD_Form SHALL accept an integer from 1 through 99.
6. WHEN a visitor enters a phone number, THE COD_Form SHALL normalize and validate the value as a Colombian_Phone_Number before submission.
7. WHEN the Order_Service receives a submission, THE Order_Service SHALL independently validate and normalize every customer field, quantity, and Colombian_Phone_Number before fraud evaluation.
8. IF a submission contains a missing field, an out-of-range field, a non-integer quantity, or an invalid Colombian_Phone_Number, THEN THE Order_Service SHALL reject the submission with field-specific errors without creating an Order.
9. WHEN the Order_Service accepts a Valid_Order_Submission, THE Order_Service SHALL capture the source Product, source Landing, normalized customer fields, quantity, request IP address, request user agent, and creation timestamp.
10. WHEN the Order_Service stores a request user agent containing no more than 512 characters, THE Order_Service SHALL preserve the received user-agent value.
11. WHEN the Order_Service receives a request user agent containing more than 512 characters, THE Order_Service SHALL store only the first 512 characters without rejecting the Valid_Order_Submission.
12. WHEN the Order_Service accepts a Valid_Order_Submission, THE Fraud_Prevention_Service SHALL evaluate the submission before the Order_Service classifies the Order.
13. WHEN every enabled Fraud_Check passes, THE Order_Service SHALL persist exactly one Normal_Order with `pending` status for the accepted submission.
14. WHEN one or more enabled Fraud_Check results trigger, THE Order_Service SHALL persist exactly one Flagged_Order with `flagged_fraud` status and every triggered Fraud_Flag for the accepted submission.
15. WHEN a GeoIP_Rule with the action named `block` triggers, THE Order_Service SHALL persist the Valid_Order_Submission as a reviewable Flagged_Order with a GeoIP Fraud_Flag.
16. WHEN any enabled Fraud_Check triggers for a Valid_Order_Submission, THE Order_Service SHALL return a completed submission result only after the Flagged_Order is persisted.
17. IF Order persistence fails after fraud evaluation, THEN THE Order_Service SHALL return a non-sensitive failure result without leaving a partially classified Order.
18. WHEN the Order_Service records an Order, THE Order_Service SHALL retain the referring Landing identifier and Slug for traceability.
19. THE Order_Service SHALL support Order_Status transitions from `pending` to `confirmed`, from `confirmed` to `shipped`, and from `shipped` to `delivered`.
20. THE Order_Service SHALL support an Order_Status transition from `pending`, `confirmed`, or `shipped` to `cancelled`.
21. THE Order_Service SHALL support an Administrator transition from `flagged_fraud` to `pending` or `cancelled` after dashboard review.
22. IF an Administrator requests a transition outside the defined Order_Status transitions, THEN THE Order_Service SHALL reject the transition without changing the Order.

### Requirement 6: Fraud Prevention and Configuration

**User Story:** As an Administrator, I want configurable and explainable fraud controls, so that suspicious COD orders remain reviewable while abusive submissions are contained.

#### Acceptance Criteria

1. WHEN a Valid_Order_Submission is received, THE Fraud_Prevention_Service SHALL evaluate duplicate detection, Manual_Blacklist matching, Rate_Limit thresholds, and enabled GeoIP_Rules synchronously before Order classification.
2. WHEN duplicate detection evaluates a Valid_Order_Submission, THE Fraud_Prevention_Service SHALL compare Orders created within the configured Duplicate_Window using all configured Duplicate_Match_Fields together.
3. WHERE the Administrator has not changed duplicate settings, THE Fraud_Prevention_Service SHALL use a 24-hour Duplicate_Window and normalized phone number plus IP address as Duplicate_Match_Fields.
4. WHEN a submission matches an Order under the duplicate configuration, THE Fraud_Prevention_Service SHALL create a duplicate Fraud_Flag containing the matched fields and Duplicate_Window.
5. WHEN a submitted normalized phone number or IP address matches a Manual_Blacklist entry, THE Fraud_Prevention_Service SHALL create a Manual_Blacklist Fraud_Flag containing the entry type and reason.
6. WHEN an Administrator adds a Manual_Blacklist entry that satisfies the Manual_Blacklist_Validity_Requirements, THE Fraud_Prevention_Service SHALL persist the entry with a creation timestamp.
7. IF an Administrator adds a duplicate Manual_Blacklist value of the same type, THEN THE Fraud_Prevention_Service SHALL reject the entry without changing the existing entry.
8. WHEN an Administrator removes a Manual_Blacklist entry, THE Fraud_Prevention_Service SHALL exclude the removed entry from subsequent submission evaluations while preserving historical Fraud_Flags.
9. WHEN the phone-number attempt count including the current attempt exceeds the configured maximum within the configured rolling window, THE Fraud_Prevention_Service SHALL create a phone Rate_Limit Fraud_Flag.
10. WHEN the IP-address attempt count including the current attempt exceeds the configured maximum within the configured rolling window, THE Fraud_Prevention_Service SHALL create an IP Rate_Limit Fraud_Flag.
11. WHERE the Administrator has not changed Rate_Limit settings, THE Fraud_Prevention_Service SHALL permit five attempts per ten-minute rolling window and create the applicable Rate_Limit Fraud_Flag on the sixth attempt independently for each normalized phone number and IP address.
12. WHEN a Valid_Order_Submission reaches fraud evaluation, THE Fraud_Prevention_Service SHALL include the current attempt in the rolling-window count used for the current Rate_Limit evaluation and subsequent Rate_Limit evaluations regardless of Order classification.
13. WHEN an enabled GeoIP_Rule matches the country or region resolved from the request IP address, THE Fraud_Prevention_Service SHALL create a GeoIP Fraud_Flag identifying the matched location and configured action.
14. WHEN an enabled GeoIP_Rule with the action named `flag` matches the resolved request location, THE Fraud_Prevention_Service SHALL classify the submission for persistence as a Flagged_Order.
15. WHEN an enabled GeoIP_Rule with the action named `block` matches the resolved request location, THE Fraud_Prevention_Service SHALL classify the submission for persistence as a Flagged_Order rather than discard or suppress the Valid_Order_Submission.
16. WHEN GeoIP lookup is enabled, THE Fraud_Prevention_Service SHALL resolve locations through the self-hosted GeoIP_Database without calling a paid external geolocation API.
17. IF the GeoIP_Database cannot resolve an IP address, THEN THE Fraud_Prevention_Service SHALL record the unresolved result and continue evaluating the remaining Fraud_Check rules.
18. IF the GeoIP_Database is unavailable, THEN THE Fraud_Prevention_Service SHALL record the unavailable result and continue evaluating the remaining Fraud_Check rules without treating the unavailable lookup as a matched GeoIP_Rule.
19. WHEN multiple Fraud_Check results trigger for one submission, THE Fraud_Prevention_Service SHALL preserve one Fraud_Flag for each triggered rule on the Flagged_Order.
20. WHEN an Administrator updates valid Fraud_Configuration values, THE Fraud_Prevention_Service SHALL apply the stored values to subsequent submissions without an application deployment.
21. IF an Administrator submits a non-positive Duplicate_Window, an empty Duplicate_Match_Fields selection, a non-positive Rate_Limit threshold, a non-positive Rate_Limit window, or an unsupported GeoIP action, THEN THE Fraud_Prevention_Service SHALL reject the update with field-specific errors without replacing the active Fraud_Configuration.
22. WHILE an Order has `flagged_fraud` status, THE Admin_Dashboard SHALL display every stored Fraud_Flag for Administrator review.
23. WHEN any Fraud_Check triggers for a Valid_Order_Submission, THE Fraud_Prevention_Service SHALL provide the complete classification result to the Order_Service without silently dropping the submission.
24. IF a proposed Manual_Blacklist entry fails any of the Manual_Blacklist_Validity_Requirements, THEN THE Fraud_Prevention_Service SHALL reject the entry with a field-specific validation error without persisting the entry.

### Requirement 7: Administrator Authentication and Access Control

**User Story:** As an Administrator, I want authenticated access to operational data, so that customer and configuration information is not publicly exposed.

#### Acceptance Criteria

1. WHEN an Administrator submits valid credentials, THE Authentication_Service SHALL issue a signed JWT containing an issuance time, expiration time, issuer, audience, and Administrator identity.
2. IF a login request contains invalid credentials, THEN THE Authentication_Service SHALL return a generic authentication error without identifying which credential failed.
3. WHEN an authenticated dashboard request includes a valid unexpired JWT with the expected signature, issuer, audience, and algorithm, THE Authentication_Service SHALL authorize the request for the Administrator role.
4. IF a private API request lacks a JWT or contains an expired, altered, incorrectly signed, or otherwise invalid JWT, THEN THE Authentication_Service SHALL reject the request with a generic authentication error.
5. THE Admin_Dashboard SHALL provide one Administrator role for the MVP.
6. WHEN the Authentication_Service stores Administrator credentials, THE Authentication_Service SHALL store a uniquely salted memory-hard password hash rather than a plaintext password.
7. WHEN the Admin_Dashboard transmits credentials, customer data, or JWT values, THE Cloud_Deployment SHALL protect the transmission with TLS.
8. WHEN an Administrator session expires, THE Authentication_Service SHALL require successful authentication before authorizing another private API request.
9. IF login attempts exceed the configured login threshold within the configured rolling window, THEN THE Authentication_Service SHALL reject additional login attempts until the rolling-window count falls below the threshold.
10. WHEN the Authentication_Service processes a successful or failed login, THE Authentication_Service SHALL record the event result and timestamp in Audit_History without recording the submitted password or JWT value.
11. IF an authenticated Administrator requests an endpoint outside the documented Administrator API and Operational_Read_Interface or requests a mutation through the Operational_Read_Interface, THEN THE Authentication_Service SHALL reject the request without exposing protected data.
12. THE COD_Commerce_Platform SHALL expose outside the normal Administrator business API only the specifically documented Operational_Read_Interface.
13. WHEN an Administrator requests the Operational_Read_Interface, THE Authentication_Service SHALL require a valid Administrator session before returning Non_Sensitive_Operational_Information.
14. WHERE the Operational_Read_Interface is available, THE Operational_Read_Interface SHALL permit read-only retrieval of Non_Sensitive_Operational_Information.
15. IF a request to the Operational_Read_Interface seeks customer data, secrets, application log content, diagnostic stack details, or an operational mutation, THEN THE Operational_Read_Interface SHALL reject the request without releasing the requested content.

### Requirement 8: Admin Dashboard Operations

**User Story:** As an Administrator, I want one dashboard for products, Landings, Orders, fraud controls, and reporting, so that I can operate the COD store without Shopify.

#### Acceptance Criteria

1. WHEN an Administrator opens product management, THE Admin_Dashboard SHALL provide Product creation, viewing, editing, Soft_Deletion, activation, and pausing controls.
2. WHEN an Administrator confirms Product deletion, THE Admin_Dashboard SHALL identify the operation as retirement and indicate that historical Orders and references remain preserved.
3. WHEN an Administrator opens Landing management, THE Admin_Dashboard SHALL provide Banner upload, removal, ordering, alternative-text, publication-status, Slug, CTA_Placement_Mode, and COD_Form presentation controls.
4. WHEN an Administrator opens order management, THE Admin_Dashboard SHALL list Orders with filters for Order_Status, Product, Landing, and inclusive creation-date range.
5. WHEN an Administrator combines supported Order filters, THE Admin_Dashboard SHALL return Orders satisfying all selected filters.
6. WHEN an Administrator opens an Order, THE Admin_Dashboard SHALL display customer delivery fields, Product and Landing attribution, request metadata, Order_Status, creation timestamp, and Fraud_Flags.
7. WHEN an Administrator selects a permitted Order_Status transition, THE Admin_Dashboard SHALL submit the requested transition to the Order_Service.
8. WHEN the Order_Service confirms a permitted Order_Status transition, THE Admin_Dashboard SHALL display the stored resulting status.
9. IF the Order_Service rejects an Order_Status transition, THEN THE Admin_Dashboard SHALL display the rejection without displaying an unpersisted status.
10. WHEN an Administrator opens fraud settings, THE Admin_Dashboard SHALL provide controls for Duplicate_Window, Duplicate_Match_Fields, Manual_Blacklist entries, Rate_Limit values, and GeoIP_Rules.
11. WHEN an Administrator requests a dashboard date range, THE Analytics_Service SHALL return Orders per calendar day for the selected range.
12. WHEN an Administrator requests Landing analytics for a date range, THE Analytics_Service SHALL return views, CTA clicks, Orders, and Conversion_Rate per Landing for the selected range.
13. WHEN an Administrator requests fraud analytics for a date range, THE Analytics_Service SHALL return Flagged_Order counts and Flagged_Fraud_Rate per calendar day for the selected range.
14. WHEN a public Landing is successfully displayed, THE Analytics_Service SHALL record one Landing view attributed to the Landing without storing additional customer contact fields.
15. WHEN a visitor activates a Landing CTA, THE Analytics_Service SHALL record one CTA click attributed to the Landing.
16. WHEN an Administrator requests CSV_Export using active Order filters, THE Order_Service SHALL generate a CSV_Export containing only the filtered Order records.
17. WHEN the Order_Service generates a CSV_Export, THE Order_Service SHALL include a header row and encode the file for import by common spreadsheet applications.
18. WHEN a customer-provided CSV_Export value begins with a spreadsheet formula control character, THE Order_Service SHALL encode the value as non-executable spreadsheet data while preserving merchant-readable content.
19. WHEN the Admin_Dashboard displays a field-specific validation error, THE Admin_Dashboard SHALL associate the error with the corresponding control and expose the error to assistive technology.
20. WHEN an Administrator operates product, Landing, Order, fraud, analytics, or export controls using a keyboard, THE Admin_Dashboard SHALL provide visible focus and keyboard activation for each interactive control.
21. IF the Analytics_Service calculates Conversion_Rate with zero Landing views or Flagged_Fraud_Rate with zero Orders, THEN THE Analytics_Service SHALL return zero for the applicable rate.
22. IF CSV header creation or spreadsheet-safe value encoding fails, THEN THE Order_Service SHALL fail CSV_Export generation atomically and return no partial CSV_Export.

### Requirement 9: Cloud-Native Deployment and Operations

**User Story:** As a platform owner, I want a reproducible cloud-native deployment, so that the MVP can run on managed cloud services without recurring storefront infrastructure services.

#### Acceptance Criteria

1. THE Cloud_Deployment SHALL deploy the frontend to Cloudflare_Pages and the backend to Koyeb as a single FastAPI Docker container connected to PostgreSQL, Upstash_Redis, and R2_Image_Storage.
2. THE Cloud_Deployment SHALL persist application records in PostgreSQL and source images and Image_Variants in R2_Image_Storage independently of backend container restarts or redeployment on Koyeb.
3. THE Cloud_Deployment SHALL provide configuration through environment variables for PostgreSQL credentials, Upstash_Redis credentials, R2_Image_Storage credentials, JWT signing secrets, GeoIP settings, and deployment-specific values.
4. THE Cloud_Deployment SHALL keep secret values outside committed source-controlled configuration files.
5. THE Cloud_Deployment SHALL route public traffic through Cloudflare_DNS to the Koyeb-hosted backend and to Cloudflare_Pages, and keep direct PostgreSQL and Upstash_Redis connection endpoints outside public exposure.
6. WHEN a public HTTP request reaches Cloudflare_DNS, THE Cloud_Deployment SHALL redirect the request to HTTPS.
7. WHEN Cloudflare_Pages or Koyeb serves the platform, THE Cloud_Deployment SHALL support TLS, HTTP/2, and compression for eligible text assets.
8. WHEN Cloudflare_DNS receives an API request, THE Cloud_Deployment SHALL route the request to the backend service on Koyeb.
9. WHEN Cloudflare_Pages receives an SPA route request, THE Cloud_Deployment SHALL serve the frontend static build with browser-routing fallback.
10. WHEN Cloudflare receives an Image_Variant request, THE Cloud_Deployment SHALL serve the file directly from R2_Image_Storage.
11. THE Cloud_Deployment SHALL keep External_CDN services outside the public request path.
12. THE Cloud_Deployment SHALL rely on managed Neon automated backups to provide PostgreSQL data durability without a custom backup job.
13. THE Cloud_Deployment SHALL use the configured Neon backup retention policy to govern how long PostgreSQL backups are retained.
14. IF a Neon-managed PostgreSQL backup fails, THEN THE Cloud_Deployment SHALL record the failure result for Operational_Read_Interface reporting without altering existing valid backups.
15. WHEN a backup verification operation runs, THE Cloud_Deployment SHALL confirm that the selected Neon backup or recovery point can restore a valid PostgreSQL database.
16. WHEN the GeoIP_Database update schedule runs, THE Cloud_Deployment SHALL activate the downloaded database only after validating the database file.
17. IF a downloaded GeoIP_Database fails validation, THEN THE Cloud_Deployment SHALL preserve the last validated GeoIP_Database and record the update failure.
18. WHEN the Koyeb backend service is redeployed or rolled back, THE Cloud_Deployment SHALL preserve PostgreSQL data and R2_Image_Storage.
19. THE Cloud_Deployment SHALL exclude dedicated database connection-pooler services, multi-node application orchestration, and horizontal replicas from the MVP.
20. THE Cloud_Deployment SHALL deliver runtime Landing, image, analytics, and GeoIP requests using only Cloudflare, Koyeb, Neon, and Upstash managed services without an additional paid external SaaS dependency.
21. THE Cloud_Deployment SHALL exclude External_CDN, external image service, and SaaS fallback activation during normal operation, Upload_Pipeline_Outage, and maintenance.

### Requirement 10: Security, Privacy, and Auditability

**User Story:** As a platform owner, I want customer and operational data protected, so that the COD workflow limits avoidable security and privacy exposure.

#### Acceptance Criteria

1. WHEN the backend receives Product, Banner, image, customer, quantity, price, or user-agent input, THE COD_Commerce_Platform SHALL enforce the applicable Domain_Validation_Limits defined in Requirements 2 through 5 before persistence or command execution.
2. WHEN the backend receives other public or private input, THE COD_Commerce_Platform SHALL validate documented type, length, format, and allowed-value constraints before persistence or command execution.
3. WHEN the backend writes or queries application records, THE COD_Commerce_Platform SHALL use Prisma_ORM with parameterized database operations.
4. WHEN the Admin_Dashboard renders customer-provided text, THE Admin_Dashboard SHALL encode the text for the output context.
5. WHEN the COD_Commerce_Platform records application logs, THE COD_Commerce_Platform SHALL redact passwords, JWT values, database credentials, full customer addresses, and full sensitive Order records.
6. WHEN the COD_Commerce_Platform stores an Order, THE Order_Service SHALL retain only the customer, attribution, and request data defined for COD fulfillment, Fraud_Check evaluation, analytics, and Audit_History.
7. WHEN a public error occurs, THE COD_Commerce_Platform SHALL return a non-sensitive error response and record diagnostic detail in platform operational logs without recording secrets or full sensitive records.
8. IF an uploaded file violates the Supported_Source_Image media types or Image_Validation_Limits, THEN THE Image_Pipeline SHALL reject the file before public availability according to Requirement 4.
9. WHEN an Administrator requests private Product, Landing, Order, fraud, analytics, Audit_History, or CSV_Export data, THE Authentication_Service SHALL require a valid Administrator session before releasing the data.
10. WHEN an Administrator changes Fraud_Configuration, Product availability, Product retirement, Landing publication, Manual_Blacklist data, Banner ordering, or Order_Status, THE COD_Commerce_Platform SHALL record the Administrator identity, action type, target identifier, result, and timestamp in Audit_History.
11. WHEN the COD_Commerce_Platform records a failed authentication or authorization event, THE COD_Commerce_Platform SHALL record the event type, result, and timestamp in Audit_History without recording credentials or JWT values.
12. WHEN the Order_Service exports customer-provided values, THE Order_Service SHALL neutralize spreadsheet formula execution according to Requirement 8.
13. WHEN the Image_Pipeline derives a storage path for an uploaded file, THE Image_Pipeline SHALL use a primary Opaque_Image_Identifier that prevents the client filename from selecting or overwriting a storage path.
14. WHEN the COD_Commerce_Platform processes a URL or redirect destination supplied by a client, THE COD_Commerce_Platform SHALL restrict the destination to documented local routes or approved origins.
15. WHEN the Cloud_Deployment accesses PostgreSQL or R2_Image_Storage, THE Cloud_Deployment SHALL use service credentials limited to the required records and files.
16. THE COD_Commerce_Platform SHALL keep customer data, project code, secrets, and operational diagnostics outside third-party analytics, monitoring, debugging, and artificial-intelligence services.
17. WHEN the COD_Commerce_Platform applies a retention or deletion operation to customer data, THE COD_Commerce_Platform SHALL preserve Order and Audit_History records required by the documented retention policy and historical-reference requirements.
18. WHEN a GeoIP_Rule action named `block` triggers for a Valid_Order_Submission, THE COD_Commerce_Platform SHALL preserve the submission as a reviewable Flagged_Order according to Requirements 5 and 6.
19. IF primary Opaque_Image_Identifier generation fails, THEN THE Image_Pipeline SHALL invoke an independent safe platform-controlled generator to create a fallback Opaque_Image_Identifier whose generation and resulting storage path are unaffected by the client filename, client-controlled path content, or the failed primary-generation mechanism.
20. IF primary and fallback Opaque_Image_Identifier generation both fail, THEN THE Image_Pipeline SHALL reject the upload, remove partial files, and omit a usable Banner association.
21. WHEN the Operational_Read_Interface returns Non_Sensitive_Operational_Information, THE Operational_Read_Interface SHALL omit application log content and the sensitive data categories excluded by the Operational_Read_Interface definition.
